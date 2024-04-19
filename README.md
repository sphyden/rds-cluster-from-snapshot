# sre-staging-db-deployer
Restores production db snapshots to staging db clusters, and updates the relevant ECS service to use the new staging DB.

### Note: You will need to be connected to the RT-Engineering VPN

## On MacOS or Linux:
### Clone the repo:
```
git clone git@github.com:RoosterTeethProductions/sre-staging-db-deployer.git

cd sre-staging-db-deployer
```

### Setup virual environment to not conflict with your local python env:
```
python3 -m venv venv
source venv/bin/activate
```
### Install dependencies in virtual environment:
```
pip install -r requirements.txt
```
### Running the script:
After this, you can invoke the script by running it in the following manner:
```
./staging-db-deployer.py <name-of-production-db-target> 
```
The `<name-of-production-db-target>` will be the production db cluster that you wish to restore into a staging cluster. Currently,
  only the following DBs supported:
  ```
  rtv3-svod-be-prod
  rtv3-lists-prod
  ```
  If we see the need to add other db's, please put in an SRE ticket, so it can be added to the config.
  
So, for example, the only current methods of running this script is as follows:
  ```
  ./staging-db-deployer.py rtv3-svod-be-prod
  ```
  or
  ```
  ./staging-db-deployer.py rtv3-lists-prod
  ```
### NOTE: The current version of this script does not delete the old staging database, so please put in a ticket to have the SRE's do this
### after it is deemed that the new staging db is stable and usable.

## Updating:
To make sure the code is up to date, and you have the latest and greatest config:

Make sure you are not in the virtual env, if you are run:
```
deactivate
```
Make sure you are in the sre-staging-db-deployer repo:
```
cd <path>/sre-staging-db-deployer
git pull
```
And you are up to date!
