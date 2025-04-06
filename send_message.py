import json
import boto3

sns_client = boto3.client('sns')
sns_topic_arn = 'arn:aws:sns:us-west-2:571600859121:testtopic'


def lambda_handler(event, context):
    response = sns_client.publish(
        TopicArn=sns_topic_arn,
        Message=json.dumps(event),
        Subject='待機後のメッセージだよーーーーー'
    )
    return {
        'statusCode': 200,
        'body': json.dumps('Hello from Lambda!')
    }
