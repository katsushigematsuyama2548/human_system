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
    
    # SESでメール送信
    send_email_with_ses(teams_message)
    
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

def create_mailto_link(json_data):
    """JSON形式のデータを使ってメール下書きリンクを作成する"""
    to = os.environ.get('GET_LOG_EMAIL_ADDRESS')
    
    # JSON文字列をパースして必要なデータを取得
    data = json.loads(json_data)
    
    # タイトルにシステム名を設定
    subject = f"ログ取得API実行: {data['system']}"
    
    # ボディに申請者と理由をJSON形式で含める - 英語のキーに統一
    body_json = {
        "mail": data['mail'],
        "content": data['content'],
        "system": data['system']
    }
    
    # JSON文字列をボディに設定
    body = json.dumps(body_json, ensure_ascii=False)
    
    params = {
        'subject': subject,
        'body': body
    }
    
    query_string = urllib.parse.urlencode(params)
    mailto_link = f"mailto:{to}?{query_string}"
    
    return mailto_link

def send_email_with_ses(message):
    """SESを使ってシンプルなHTML形式のメールを送信する"""
    ses = boto3.client('ses')
    
    # リンクを取得
    mailto_link = message['承認メール作成'].split(': ')[1]
    
    # 送信先メールアドレス（環境変数から取得）
    recipient = os.environ.get('TEAMS_NOTIFICATION_EMAIL')
    
    # シンプルなHTML形式のメール本文を作成
    html_body = f"""
    <html>
    <body>
        <p>申請システム: {message['申請システム']}</p>
        <p>申請者アドレス: {message['申請者アドレス']}</p>
        <p>申請内容: {message['申請内容'].replace('\\n', '<br>')}</p>
        <p>承認メール作成: <a href="{mailto_link}">承認メールを作成する</a></p>
        <p>※承認する場合は、開いた下書きメールをそのまま送信してください。</p>
    </body>
    </html>
    """
    
    # プレーンテキスト版
    text_body = f"""
        申請システム: {message['申請システム']}
        申請者アドレス: {message['申請者アドレス']}
        申請内容: {message['申請内容']}

        承認メール作成: {mailto_link}
        
        ※承認する場合は、開いた下書きメールをそのまま送信してください。
    """
    
    try:
        response = ses.send_email(
            Source=os.environ.get('FROM_EMAIL_ADDRESS'),
            Destination={
                'ToAddresses': [recipient]
            },
            Message={
                'Subject': {
                    'Data': "ログ取得API承認依頼"
                },
                'Body': {
                    'Text': {
                        'Data': text_body
                    },
                    'Html': {
                        'Data': html_body
                    }
                }
            }
        )
        return response
    except Exception as e:
        print(f"SES送信エラー: {str(e)}")
        raise e
