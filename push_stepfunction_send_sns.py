import json
import boto3

sns_client = boto3.client('sns')
sfn_client = boto3.client('stepfunctions')

SNS_TOPIC_ARN = "arn:aws:sns:us-west-2:571600859121:testtopic"

def lambda_handler(event, context):
    print("Callback Lambda event:", json.dumps(event, ensure_ascii=False))
    
    # 待機タスクから渡される taskToken を取得
    task_token = event.get('taskToken')
    if not task_token:
        raise Exception("taskToken がイベントに含まれていません")
    
    callback_info = event.get('callbackInfo', '情報なし')
    
    # タスクトークンを含むリンクを作成（例: API Gateway 経由のエンドポイント）
    base_url = "https://4ds3ufmetf.execute-api.us-west-2.amazonaws.com/dev/restart/"
    link = f"{base_url}{task_token}"
    
    # SNSで送信するメッセージ作成
    sns_message = (
        f"Step Functions の待機タスクが実行中です。\n"
        f"taskToken: {task_token}\n"
        f"callbackInfo: {callback_info}\n"
        f"タスクを再開するには以下のリンクをクリックしてください:\n{link}"
    )
    
    try:
        sns_response = sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Message=sns_message,
            Subject="Step Functions Callback: タスクトークン付きリンク"
        )
        print("SNS publish response:", sns_response)
    except Exception as e:
        print("Error publishing SNS:", str(e))
        return {
            "statusCode": 500,
            "body": json.dumps("SNS への通知に失敗しました")
        }
    
    # このLambdaではタスクトークンをSNSで送信するだけなので、ここではタスクの再開は行いません。
    # ユーザーがリンクをクリックした後、別のLambdaが send_task_success/send_task_failure を呼び出して待機タスクを完了させます。
    
    return {
        "statusCode": 200,
        "body": json.dumps("Callback Lambda が SNS への通知を完了しました")
    }
