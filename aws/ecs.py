import boto3

boto3.setup_default_session(region_name='us-east-1')

class ECS(object):
    def __init__(self):
        self.ecs = boto3.client('ecs')
        """:type: pyboto3.ecs"""