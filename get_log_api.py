import json
import boto3
import email
import urllib.parse
import paramiko
import os
import tempfile
from datetime import datetime

def lambda_handler(event, context):
    # SESイベントからメール情報を取得
    ses_notification = event['Records'][0]['ses']
    message_id = ses_notification['mail']['messageId']
    
    # 送信元アドレスをログに記録（監査目的）
    sender_email = ses_notification['mail']['source']
    print(f"承認メールを受信: {sender_email}")
    
    # S3からメール本文を取得
    mail_body = get_email_from_s3(message_id)
    
    # メール本文からJSONデータを抽出
    try:
        request_data = json.loads(mail_body)
        target_system = request_data.get('system')
        requester_email = request_data.get('mail')
        request_reason = request_data.get('content')
        
        if not all([target_system, requester_email]):
            raise ValueError("必要なデータがメール本文に含まれていません")
            
    except (json.JSONDecodeError, ValueError) as e:
        print(f"メール本文の解析エラー: {str(e)}")
        return {
            'statusCode': 400,
            'body': json.dumps('メール形式が不正です')
        }
    
    # パラメータストアからログパス情報を取得
    log_config = get_log_config_from_parameter_store(target_system)
    
    # ログ取得結果を格納するリスト
    log_results = []
    
    # 各サーバーに接続してログを取得
    for server_id, server_config in log_config.get('servers', {}).items():
        # シークレットマネージャーからサーバー接続情報を取得
        server_secret = get_server_credentials(server_id)
        
        # 各ログパスに対してログを取得
        for log_path in server_config.get('log_paths', []):
            log_file = fetch_logs_via_ssh(
                server_secret['host'],
                server_secret['username'],
                server_secret['password'],
                log_path
            )
            
            if log_file:
                # S3にログをアップロード
                s3_path = upload_log_to_s3(log_file, target_system, server_id, log_path)
                log_results.append({
                    'server': server_id,
                    'log_path': log_path,
                    's3_path': s3_path,
                    'status': 'success'
                })
            else:
                log_results.append({
                    'server': server_id,
                    'log_path': log_path,
                    'status': 'failed'
                })
    
    # ログ取得結果をTeamsに送信
    send_logs_notification_to_teams(target_system, log_results)
    
    # 申請情報を別のTeamsに送信
    send_request_info_to_teams(requester_email, target_system, request_reason)
    
    return {
        'statusCode': 200,
        'body': json.dumps('ログ取得が完了しました')
    }

def get_email_from_s3(message_id):
    """S3からメール本文を取得する"""
    s3 = boto3.client('s3')
    bucket_name = os.environ.get('S3_BUCKET_NAME')
    
    try:
        response = s3.get_object(Bucket=bucket_name, Key=f"emails/{message_id}")
        email_content = response['Body'].read().decode('utf-8')
        
        # メールをパース
        msg = email.message_from_string(email_content)
        
        # メール本文を取得
        mail_body = ""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain":
                    mail_body = part.get_payload(decode=True).decode('utf-8')
                    break
        else:
            mail_body = msg.get_payload(decode=True).decode('utf-8')
            
        return mail_body
    except Exception as e:
        print(f"S3からのメール取得エラー: {str(e)}")
        raise e

def get_log_config_from_parameter_store(system_name):
    """パラメータストアからログ設定を取得する"""
    ssm = boto3.client('ssm')
    parameter_name = f"/log-api/{system_name}"
    
    try:
        response = ssm.get_parameter(
            Name=parameter_name,
            WithDecryption=True
        )
        return json.loads(response['Parameter']['Value'])
    except Exception as e:
        print(f"パラメータストアからの設定取得エラー: {str(e)}")
        raise e

def get_server_credentials(server_id):
    """シークレットマネージャーからサーバー接続情報を取得する"""
    secretsmanager = boto3.client('secretsmanager')
    secret_name = f"/log-api/servers/{server_id}"
    
    try:
        response = secretsmanager.get_secret_value(
            SecretId=secret_name
        )
        return json.loads(response['SecretString'])
    except Exception as e:
        print(f"シークレットマネージャーからの接続情報取得エラー: {str(e)}")
        raise e

def fetch_logs_via_ssh(host, username, password, log_path):
    """SSHを使用してサーバーからログを取得する"""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        # SSHで接続
        ssh.connect(hostname=host, username=username, password=password)
        
        # ファイル存在確認
        stdin, stdout, stderr = ssh.exec_command(f"ls -la {log_path}")
        if stderr.read():
            print(f"ログファイルが存在しません: {log_path}")
            return None
        
        # 一時ファイルを作成
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file_path = temp_file.name
        
        # SCPでファイルを取得
        sftp = ssh.open_sftp()
        sftp.get(log_path, temp_file_path)
        sftp.close()
        
        return temp_file_path
    except Exception as e:
        print(f"SSH接続またはログ取得エラー: {str(e)}")
        return None
    finally:
        ssh.close()

def upload_log_to_s3(local_file_path, system_name, server_id, log_path):
    """ログファイルをS3にアップロードする"""
    if not local_file_path:
        return None
        
    s3 = boto3.client('s3')
    bucket_name = os.environ.get('LOG_BUCKET_NAME')
    
    # ログファイル名を取得
    log_file_name = os.path.basename(log_path)
    
    # 日付ベースのパス生成
    now = datetime.now()
    date_path = now.strftime("%Y/%m/%d")
    
    # S3内のパス
    s3_key = f"{system_name}/{server_id}/{date_path}/{log_file_name}"
    
    try:
        with open(local_file_path, 'rb') as file:
            s3.upload_fileobj(file, bucket_name, s3_key)
        
        # 一時ファイルを削除
        os.remove(local_file_path)
        
        return f"s3://{bucket_name}/{s3_key}"
    except Exception as e:
        print(f"S3アップロードエラー: {str(e)}")
        # エラー時も一時ファイルを削除
        if os.path.exists(local_file_path):
            os.remove(local_file_path)
        return None

def send_logs_notification_to_teams(system_name, log_results):
    """ログ取得結果をTeamsに送信する"""
    sns = boto3.client('sns')
    topic_arn = os.environ.get('LOG_NOTIFICATION_SNS_TOPIC')
    
    # 成功したログ取得のS3パスリスト
    successful_logs = [result for result in log_results if result['status'] == 'success']
    failed_logs = [result for result in log_results if result['status'] == 'failed']
    
    # メッセージ作成
    message = f"""
システム「{system_name}」のログ取得が完了しました。

取得成功ログ: {len(successful_logs)}/{len(log_results)}
"""
    
    # 成功したログのS3パスを追加
    if successful_logs:
        message += "\n取得したログファイル:\n"
        for log in successful_logs:
            message += f"- {log['server']}: {log['log_path']} → {log['s3_path']}\n"
    
    # 失敗したログがあれば情報を追加
    if failed_logs:
        message += "\n取得失敗したログ:\n"
        for log in failed_logs:
            message += f"- {log['server']}: {log['log_path']}\n"
    
    try:
        response = sns.publish(
            TopicArn=topic_arn,
            Message=message,
            Subject=f"ログ取得完了: {system_name}"
        )
        return response
    except Exception as e:
        print(f"SNS送信エラー (ログ通知): {str(e)}")
        raise e

def send_request_info_to_teams(requester_email, system_name, request_reason):
    """申請情報を別のTeamsに送信する"""
    sns = boto3.client('sns')
    topic_arn = os.environ.get('REQUEST_INFO_SNS_TOPIC')
    
    message = f"""
ログ取得申請情報:

申請者: {requester_email}
申請システム: {system_name}
申請理由: {request_reason}
取得日時: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""
    
    try:
        response = sns.publish(
            TopicArn=topic_arn,
            Message=message,
            Subject=f"ログ取得申請: {system_name}"
        )
        return response
    except Exception as e:
        print(f"SNS送信エラー (申請情報): {str(e)}")
        raise e