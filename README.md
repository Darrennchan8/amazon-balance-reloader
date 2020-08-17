# Amazon Balance Loader
This is a Flask server that provides functionality to refill the gift card balance of an associated Amazon account.

## Motivation
Many credit card companies close credit cards due to inactivity, which can lead to a dip one's personal credit score.
Sources: [1](https://www.nerdwallet.com/article/credit-cards/credit-card-cancelled-due-inactivity),
[2](https://www.quickenloans.com/blog/credit-card-inactivity-impact-credit-score),
[3](https://www.equifax.com/personal/education/credit/report/inactive-credit-card-account-closed/),
[4](https://www.moneyunder30.com/will-my-credit-score-go-down-if-a-credit-card-company-closes-my-account-for-non-use),
[5](https://www.creditkarma.com/credit-cards/i/keep-accounts-active).

When maximizing credit card rewards, especially with cards that have rotating categories or older credit cards, one
might not have any reason to a particular card for an extended period of time due to the rewards structure, risking
account closure due to credit card inactivity.

This project seeks to provide a means to automatically charge any amount against your credit/debit card(s) to mitigate
credit card inactivity.

## Local Setup
### Prerequisites
- Python 3.8 or greater
- pip3

### Setup
A typical flow for local setup follows:
```bash
# (Recommended) Create a python virtual environment.
python3 -m pip install virtualenv
python3 -m venv env
source env/bin/activate # Activate the virtual environment. You'll need to run this for each new terminal instance.

# Install necessary dependencies.
pip install -r requirements.txt

# (Recommended) Enable pre-commit hooks for style linting and more.
pre-commit install
```

### Cloud Firestore
Before running, you'll need to follow
[these steps](https://cloud.google.com/appengine/docs/standard/python3/quickstart#before-you-begin)
to create a new GCP project, create a
[GCP Firestore](https://cloud.google.com/firestore/docs/quickstart-servers#create_a_in_native_mode_database)
instance, and
[generate credentials for `App Engine default service account`](https://console.cloud.google.com/apis/credentials/serviceaccountkey).
You can supply authentication credentials to your local application by setting the environment variable
GOOGLE_APPLICATION_CREDENTIALS. Example:
```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/amazon-balance-reloader/service-account.json"
```

To initialize the data in Firestore, you can use `secrets.py`. Be prepared to enter your Amazon login credentials, credit card
information, and save the secret key for [later use](#usage).
```bash
# Initialize Amazon credentials.
python3 secrets.py --reset
# Add cards.
python3 secrets.py --add-cards
```

## Running Locally
Run `main.py` to start a development server on port 8080:
```bash
python3 main.py
```

Visit `http://127.0.0.1:8080/` to view an HTML dashboard containing a list of recent transactions and cards.

### Usage
This app is controlled via a REST api. Here are the routes and their descriptions:

Reload the Amazon gift card balance by using a specified card to charge a specified amount.\
`GET` `/reload?key=[SECRET_KEY]&cards=[CARD_NAMES]&amount=[AMOUNT]`
 - SECRET_KEY: The private key emitted by `secrets.py`.
 - CARD_NAMES: A series of added card names separated by a comma.
 - AMOUNT: A positive floating-point number. Note that Amazon imposes a minimum reload amount of `0.50`.

Reload the Amazon gift card balance by charging all cards associated with the Amazon account.\
`GET` `/reloadAll?key=[SECRET_KEY]&amount=[AMOUNT]`
 - SECRET_KEY: The private key emitted by `secrets.py`.
 - AMOUNT: A positive floating-point number. Note that Amazon imposes a minimum reload amount of `0.50`.

## Running on the Cloud
Before deploying on App Engine, we need to configure a remotely accessible selenium backend.

### Compute Engine Webdriver Server
Follow [these steps](https://cloud.google.com/compute/docs/instances/create-start-instance#from-container-image) to
create a new VM instance, with the
[selenium/standalone-chrome](https://hub.docker.com/r/selenium/standalone-chrome/) container image. Additionally, add
the `standalone-chrome` network tag. This will be used for locating the instance and configuring firewall rules.

After configuring the new VM instance, you can rerun the application with the `--compute-instance-webdriver` command
line flag to utilize the remote selenium backend.
```bash
python3 main.py --compute-instance-webdriver
```

#### Memory Constrained Instances
With proper configuration, a remote selenium + chromedriver backend can even run on a f1-micro instance.

It's notable that that Google fluentd (stackdriver-logging.service) can utilize a significant amount of memory, which
makes execution infeasible on f1-micro instances [(Example)](https://serverfault.com/q/980569).\
Execute these commands to disable it for the compute instance:
```bash
gcloud compute instances add-metadata <INSTANCE_NAME> --metadata="google-logging-enabled=false"
gcloud compute instances add-metadata <INSTANCE_NAME> --metadata="google-monitoring-enabled=false"
```
It is not possible to set the `google-logging-enabled=false` metadata through the web UI. In fact, changing any
configuration for the instance through web UI will automatically set `google-logging-enabled=true`.

### App Engine Deployment
This project is preconfigured for [Google App Engine](https://cloud.google.com/appengine/docs/standard/python3)
deployment.
```bash
gcloud app deploy # Select your target project.
gcloud app browse # Navigate to the hosted application.
```

## Next Steps
While the above steps are the bare necessities for a functional API for charging credit cards for your Amazon gift card
balance, you may find the below sections useful for automation needs, development convenience, and added security.

### Automated Reloading
Consider [Google Cloud Scheduler](https://cloud.google.com/scheduler) or
[cron.yaml](https://cloud.google.com/appengine/docs/standard/python3/scheduling-jobs-with-cron-yaml) to automatically
ping `/reloadAll` periodically.

Note that you will need to change the request type on Google Cloud Scheduler (default POST) to GET.

### Automated Builds
Follow [these steps](https://cloud.google.com/source-repositories/docs/integrating-with-cloud-build) to integrate with
Cloud Build Triggers for GitHub, which will allow you to automatically build whenever commits are pushed to your
repository. A build config file is preconfigured.
