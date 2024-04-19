#!/usr/bin/env python3

from config.config import Config
from aws.ecs import ECS
from aws.rds import RDS
from slack_message.slack_message import SlackMessage
import botocore.exceptions
import time
import sys
import datetime
import copy

config_file = Config()
config = config_file.get_config_file()

rds = RDS().rds
ecs = ECS().ecs
slack = SlackMessage()

#Need a datetime object for comparison purposes, as boto3 returns a datetime object fromm SnapshotCreateTime
#TODO: make time object UTC
def get_current_time():
    current_time = datetime.datetime.now()
    formatted_time = current_time.strftime('%Y-%m-%d')
    return formatted_time

def slack_print(text=""):
    if len(sys.argv) > 2:
        if sys.argv[2] == '--slack':
            print(text)
            slack.post_message(text)
    else:
        print(text)

#This is not super great, but currently we find a services DB based on the services name, this should be fine as we
#for now prepend all of our services, and thier assets the same way.
#TODO: Add logic to ensure that the current production database for a service is being targeted for the snapshot
def get_db_cluster_id(database):
    try:
        db_clusters = rds.describe_db_clusters()
        db_cluster_id = None
        for db_cluster in db_clusters['DBClusters']:
            if db_cluster.get('DBClusterIdentifier'):
                if db_cluster['DBClusterIdentifier'].startswith(database) and "staging" not in db_cluster['DBClusterIdentifier'] :
                    db_cluster_id = db_cluster['DBClusterIdentifier']
            else:
                slack_print(f"DB Cluster identifier could not be found for: {database}")
                sys.exit(0)
        return db_cluster_id
    except botocore.exceptions.ClientError as e:
        slack_print(e)
        sys.exit(1)

#This gets the latest db cluster snapshot by seeding a createtime from the list of snapshots, and then comparing in loop
#until the latest snapshot is returned
def get_latest_db_cluster_snapshot_id(db_cluster_id):
    try:
        response = rds.describe_db_cluster_snapshots(DBClusterIdentifier=db_cluster_id, SnapshotType="automated")

        if response['DBClusterSnapshots'] == []:
            slack_print(f"No Snapshots found for {db_cluster_id}")
            sys.exit(0)

        seed_db_cluster_snapshot_createtime = response['DBClusterSnapshots'][0]['SnapshotCreateTime']
        latest_db_cluster_snapshot_id = None

        for snapshot in response['DBClusterSnapshots']:
            if snapshot.get('DBClusterSnapshotIdentifier'):
                snapshot_createtime = snapshot['SnapshotCreateTime']
                if snapshot_createtime >= seed_db_cluster_snapshot_createtime:
                    latest_db_cluster_snapshot_id = snapshot['DBClusterSnapshotIdentifier']

        return latest_db_cluster_snapshot_id

    except botocore.exceptions.ClientError as e:
        slack_print(e)
        sys.exit(1)

def restore_db_cluster_from_snapshot(database, latest_snapshot, engine, engine_version):

    database_basename = database.replace('-prod', '')
    db_cluster_id = f"{database_basename}-staging-{get_current_time()}"
    subnet_group = config[database]['subnet_group']
    security_groups = config[database]['vpc_security_groups']

    try:
        response = rds.restore_db_cluster_from_snapshot(DBClusterIdentifier=db_cluster_id,
                                                        SnapshotIdentifier=latest_snapshot,
                                                        Engine=engine,
                                                        EngineVersion=engine_version,
                                                        DBSubnetGroupName=subnet_group,
                                                        VpcSecurityGroupIds=security_groups)
        return db_cluster_id
    except botocore.exceptions.ClientError as e:
        if e.response['Error']['Code'] == 'DBClusterAlreadyExistsFault':
            return db_cluster_id
        else:
            slack_print(f"Unexpected Error: {e}")
            sys.exit(1)

def create_new_db_instance(database, db_cluster_id, engine, engine_version):
    
    db_instance_id = f"{db_cluster_id}-instance-1"
    instance_class = "db.r5.large"
    subnet_group = config[database]['subnet_group']

    try:
        rds.create_db_instance(DBClusterIdentifier=db_cluster_id,
                               DBInstanceIdentifier=db_instance_id,
                               Engine=engine,
                               EngineVersion=engine_version,
                               DBInstanceClass=instance_class,
                               DBSubnetGroupName=subnet_group)

        return db_instance_id
    except botocore.exceptions.ClientError as e:
        if e.response['Error']['Code'] == 'DBInstanceAlreadyExists':
            return db_instance_id
        else:
            slack_print(f'Unexpected Error: {e}')
            sys.exit(1)

def get_db_cluster_status(db_cluster_id):
    try:
        response = rds.describe_db_clusters(DBClusterIdentifier=db_cluster_id)
        return response['DBClusters'][0]['Status']
    except botocore.exceptions.ClientError as e:
        slack_print(e)
        pass

def get_db_instance_status(db_instance_id):
    try:
        response = rds.describe_db_instances(DBInstanceIdentifier=db_instance_id)
        return response['DBInstances'][0]['DBInstanceStatus']
    except botocore.exceptions.ClientError as e:
        slack_print(e)
        pass

def get_new_db_cluster_endpoint(db_cluster_id):
    try:
        response = rds.describe_db_clusters(DBClusterIdentifier=db_cluster_id)
        return response['DBClusters'][0]['Endpoint']
    except botocore.exceptions.ClientError as e:
        slack_print(e)

def get_existing_task_definition_name(cluster, service):
    try:
        response = ecs.describe_services(cluster=cluster, services=[service])
        current_task_definition_name = response['services'][0]['deployments'][0]['taskDefinition']
        return current_task_definition_name
    except botocore.exceptions.ClientError as e:
        slack_print(e)
        sys.exit(1)

def describe_current_task_defintion(current_task_definition_name):
    try:
        response = ecs.describe_task_definition(taskDefinition=current_task_definition_name)
        return response
    except botocore.exceptions.ClientError as e:
        slack_print(e)
        sys.exit(1)

def create_new_task_definition(current_task_definition, new_db_host, db_env_var):

    task_definition = current_task_definition['taskDefinition']
    new_task_definition = copy.deepcopy(task_definition)
    aws_reserved_params = ['status',
                           'compatibilities',
                           'taskDefinitionArn',
                           'registeredAt',
                           'registeredBy',
                           'revision',
                           'requiresAttributes']

    for param in aws_reserved_params:
        if new_task_definition.get(param):
            del new_task_definition[param]

    for env_var in new_task_definition['containerDefinitions'][0]['environment']:
        if env_var['name'] == db_env_var:
            env_var['value'] = new_db_host

    return new_task_definition

def register_task_definition(new_task_definition):
    try:
        response = ecs.register_task_definition(**new_task_definition)
        return response['taskDefinition']['taskDefinitionArn']
    except botocore.exceptions.ClientError as e:
        slack_print(e)
        sys.exit(1)

def update_service(cluster, service, new_task_definition_arn):
    try:
        response = ecs.update_service(cluster=cluster, service=service, taskDefinition=new_task_definition_arn)
        return response
    except botocore.exceptions.ClientError as e:
        slack_print(e)
        sys.exit(1)

def get_deployment_status(cluster, service):
    try:
        response = ecs.describe_services(cluster=cluster, services=[service])
        deployments = response['services'][0]['deployments']
        primary_deployment = {}

        for deployment in deployments:
            if deployment['status'] == "PRIMARY":
                primary_deployment = deployment

        if primary_deployment['desiredCount'] == primary_deployment['runningCount']:
            return True
        else:
            return False
    except botocore.exceptions.ClientError as e:
        slack_print(e)
        pass

def main():
    #Parse service list from config file, make sure argument matches a service in the list
    database_list = [x for x in config.keys()]
    database = sys.argv[1]

    if database == None:
        slack_print(f"""Name of database is required (the production database that you wish to clone into staging), 
        The following databases are currently supported: ```{database_list}```""")
        sys.exit(1)
    if database not in database_list:
        slack_print(f"""Argument is malformed, or the database provided is not currently supported, 
        The following databases are currently supported: ```{database_list}```""")
        sys.exit(1)


    #Get latest snapshot after matching a service to a database
    latest_snapshot_id = get_latest_db_cluster_snapshot_id(get_db_cluster_id(database))

    #Create a new db cluster from the snapshot retrieved previously
    slack_print(f"Creating Staging Database Cluster for: {database} from snapshot: {latest_snapshot_id}")
    new_db_cluster_id = restore_db_cluster_from_snapshot(database,  latest_snapshot_id,  config[database]['engine'], config[database]['engine_version'])

    #Restoring a db cluster from snapshot takes a while, so here is some heavy handed waiting logic
    #There currently is no logic built in to boto for watiers for db cluster actions
    retries = 20
    while retries > 0:
        time.sleep(45)
        status = get_db_cluster_status(new_db_cluster_id)
        if status == "available":
            break
        retries -= 1

    #When restoring a db cluster via boto3, the instances are not automatically created for data access
    #This creates an instance for the new cluster so that data is accessible
    new_db_instance_id = create_new_db_instance(database, new_db_cluster_id, config[database]['engine'], config[database]['engine_version'])

    #Same waiting logic as the db cluster creation
    retries = 20
    while retries > 0:
        time.sleep(45)
        status = get_db_instance_status(new_db_instance_id)
        if status == "available":
            break
        retries -= 1

    #Get our new endpoint to update the ECS task with
    new_db_cluster_endpoint = get_new_db_cluster_endpoint(new_db_cluster_id)

    #Grab our config values for ECS services that are going to use the DB we created
    cluster = config[database]['ecs_cluster']
    main_service = config[database]['ecs_service']
    sk_service = config[database]['ecs_sk_service']
    db_env_var = config[database]['db_env_var']

    for service in [main_service, sk_service]:

        existing_task_definition_name = get_existing_task_definition_name(cluster, service)
        existing_task_definition = describe_current_task_defintion(existing_task_definition_name)
        new_task_definition = create_new_task_definition(existing_task_definition, new_db_cluster_endpoint, db_env_var)
        new_task_definition_arn = register_task_definition(new_task_definition)
        update_service(cluster, service, new_task_definition_arn)

        retries = 20
        while retries > 0:
            time.sleep(30)
            if get_deployment_status(cluster, service) is True:
                break
            else:
                retries -= 1

    #let user know that the db creation is complete, and the service is updated
    slack_print(f"New staging DB cluster created for {main_service}, {sk_service}: {new_db_cluster_endpoint}, and {main_service}, {sk_service} is now updated and ready to use :shyden:")

if __name__ == "__main__":
    main()
