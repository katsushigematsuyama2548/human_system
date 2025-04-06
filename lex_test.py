import json
import boto3

# SNSクライアントの初期化
sns_client = boto3.client('sns')
# 送信先のSNS Topic ARN（各自の設定に合わせてください）
SNS_TOPIC_ARN = "arn:aws:sns:us-west-2:571600859121:testtopic"

def lambda_handler(event, context):
    print("Received event:", json.dumps(event, ensure_ascii=False))
    
    # Lexのインテント情報を取得
    intent = event.get('sessionState', {}).get('intent', {})
    confirmation_state = intent.get('confirmationState', None)
    
    # 確認が完了しているかチェック（ユーザーがYesと回答して確認完了）
    if confirmation_state == "Confirmed":
        # 必要に応じてスロット情報などを利用してメッセージ内容を作成
        message_content = "人事異動の処理が確認されました。"
        
        # SNSにメッセージを送信
        try:
            response = sns_client.publish(
                TopicArn=SNS_TOPIC_ARN,
                Message=message_content,
                Subject="Lex SNS通知"
            )
            print("SNS publish response:", json.dumps(response))
        except Exception as e:
            print("Error publishing to SNS:", str(e))
            # エラー時は、必要に応じて処理を変更
            return {
                "messages": [
                    {
                        "contentType": "PlainText",
                        "content": "エラーが発生しました。"
                    }
                ],
                "sessionState": {
                    "dialogAction": {
                        "type": "Close"
                    },
                    "intent": {
                        "name": intent.get('name', ''),
                        "slots": intent.get('slots', {}),
                        "state": "Failed",
                        "confirmationState": confirmation_state
                    }
                }
            }
        
        # SNS送信後、Fulfillment完了としてクローズレスポンスを返す
        return {
            "messages": [
                {
                    "contentType": "PlainText",
                    "content": "人事異動処理が完了しました。"
                }
            ],
            "sessionState": {
                "dialogAction": {
                    "type": "Close"
                },
                "intent": {
                    "name": intent.get('name', ''),
                    "slots": intent.get('slots', {}),
                    "state": "Fulfilled",
                    "confirmationState": confirmation_state
                }
            }
        }
    
    else:
        # 確認状態が未完了の場合は、その旨を返す（必要に応じて処理を追加）
        return {
            "messages": [
                {
                    "contentType": "PlainText",
                    "content": "確認が完了していません。"
                }
            ],
            "sessionState": {
                "dialogAction": {
                    "type": "Close"
                },
                "intent": {
                    "name": intent.get('name', ''),
                    "slots": intent.get('slots', {}),
                    "state": "Failed",
                    "confirmationState": confirmation_state
                }
            }
        }
