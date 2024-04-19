import os

import boto3

boto3.setup_default_session(region_name='us-east-1')

class RDS(object):
    def __init__(self):
        self.rds = boto3.client('rds')
        """:type: pyboto3.rds"""







