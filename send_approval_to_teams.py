import json
import boto3
import email
import urllib.parse
from base64 import b64decode
import os


def lambda_handler(event, context):
    # SESイベントからメール情報を取得
    ses_notification = event['Records'][0]['ses']
    message_id = ses_notification['mail']['messageId']
    
    # イベントから直接メールタイトルと送信元を取得
    mail_subject = ses_notification['mail']['commonHeaders']['subject']
    sender_email = ses_notification['mail']['source']
    
    # S3からメール本文を取得
    mail_body = get_email_body_from_s3(message_id)
    
    # 環境変数から承認メールアドレスを取得
    approval_email = os.environ.get('APPROVAL_EMAIL_ADDRESS')
    
    # JSON形式のタイトルを作成
    title_json = {
        "mail": sender_email,
        "content": mail_body,
        "system": mail_subject
    }
    
    # JSON文字列に変換したタイトルでメール下書きリンクを作成
    draft_link = create_mailto_link(
        json.dumps(title_json, ensure_ascii=False)
    )
    
    # Teams用の承認メッセージを作成
    teams_message = create_teams_approval_message(mail_subject, sender_email, mail_body, draft_link)
    
    # SNSトピックに送信
    send_to_sns(teams_message)
    
    return {
        'statusCode': 200,
        'body': json.dumps('承認メールが正常に処理されました')
    }

def get_email_body_from_s3(message_id):
    """S3からメール本文を取得する"""
    s3 = boto3.client('s3')
    bucket_name = os.environ.get('S3_BUCKET_NAME')  # S3バケット名を設定
    
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
        return "メール本文を取得できませんでした。"

def create_teams_approval_message(subject, from_addr, body, draft_link):
    """Teams向けの承認メッセージを作成する"""
    # プレーンテキスト形式でリンクを含める
    return {
        "申請システム": subject,
        "申請者アドレス": from_addr,
        "申請内容": body,
        "承認メール作成": f"以下のリンクをクリックして承認メールを作成してください: {draft_link}"
    }

def send_to_sns(message):
    """SNSにメッセージを送信する"""
    sns = boto3.client('sns')
    sns_topic_arn = os.environ.get('SNS_TOPIC_ARN')
    
    # リンクをより認識されやすい形式に変更
    mailto_link = message['承認メール作成'].split(': ')[1]
    
    # テキスト形式のメッセージを作成（URLをそのまま表示）
    formatted_message = f"""
申請システム: {message['申請システム']}
申請者アドレス: {message['申請者アドレス']}
申請内容: {message['申請内容']}

■ 以下のURLをコピーしてブラウザに貼り付けると承認メールが作成されます ■
{mailto_link}
    """
    
    try:
        response = sns.publish(
            TopicArn=sns_topic_arn,
            Message=formatted_message,
            Subject='Teams承認通知'
        )
        return response
    except Exception as e:
        print(f"SNS送信エラー: {str(e)}")
        raise e

def create_mailto_link(subject):
    """シンプルな形式のメール下書きリンクを作成する"""
    to = os.environ.get('GET_LOG_EMAIL_ADDRESS')
    
    # JSONではなくシンプルなテキストタイトル
    simple_subject = "承認リクエスト"
    
    params = {
        'subject': simple_subject,
    }
    
    query_string = urllib.parse.urlencode(params)
    mailto_link = f"mailto:{to}?{query_string}"
    
    return mailto_link
