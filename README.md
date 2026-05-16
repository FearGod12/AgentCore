# Set-Up

## Prerequisites

- AWS Account with `AdministratorAccess` role to perform terragrunt actions
- Slack account with access to a workspace
- terragrunt and terraform installed on your PC
- Ensure you update the `docker/push_images.sh` file with your AWS Account ID

### Step 1: Create the Slack app & store secrets

- Open this url: `api.slack.com/apps` > Create New App > From Scratch

    1. App Name: agentcore-pe
    2. Workspace: Your slack workspace

- Copy the signing secret and store it temporarily

- Click on OAuth & Permissions
    1. Scroll down to `Bot Token Scopes` and add the following scopes:
            - chat:write
            - app_mentions:read
    2. Scroll up and Install to Workspace
    3. Copy the Bot User OAuth Token (xoxb-...)

- Store both secrets in AWS Secrets Manager

    1. **Signing Secret**
            ```sh
            aws secretsmanager create-secret \
            --name "agentcore/slack-signing-secret" \
            --description "Slack signing secret for request verification" \
            --secret-string '{"value":"<PASTE-SIGNING-SECRET-HERE>"}' \
            --region us-east-1
            ```

    2. **Bot Token**
            ```sh
            aws secretsmanager create-secret \
            --name "agentcore/slack-signing-secret" \
            --description "Slack signing secret for request verification" \
            --secret-string '{"value":"<PASTE-SIGNING-SECRET-HERE>"}' \
            --region us-east-1
            ```

    3. **Verify both secrets exist**
            ```sh
            aws secretsmanager list-secrets --region us-east-1 \
            --query "SecretList[?starts_with(Name,'agentcore/slack')].Name" \
            --output text

            # Expected Output:
            # agentcore/slack-signing-secret    agentcore/slack-bot-token
            ```

### Step 2: Deploying Infrastructure sequentially

- Deploy **base**
        ```sh
        cd live/base
        terragrunt plan; terragrunt apply -auto-approve
        ```

- Build and Push Docker Image to the ECR created after the base has been deployed successfully
        ```sh
        cd docker
        sh push_images.sh
        ```

- Deploy **VPC**
        ```sh
        cd live/vpc
        terragrunt plan; terragrunt apply -auto-approve
        ```

- Deploy **Security Groups**
        ```sh
        cd live/security_groups
        terragrunt plan; terragrunt apply -auto-approve
        ```

- Deploy **VPC Endpoint**
        ```sh
        cd live/vpc_endpoint
        terragrunt plan; terragrunt apply -auto-approve
        ```

- Deploy **AgentCore Gateway**
        ```sh
        cd live/gateway
        terragrunt plan; terragrunt apply -auto-approve
        ```

- Deploy **AgentCore Runtime**
        ```sh
        cd live/runtime
        terragrunt plan; terragrunt apply -auto-approve
        ```

- Deploy **Slack Handler**
        ```sh
        cd live/slack_handler
        terragrunt plan; terragrunt apply -auto-approve
        ```

- Deploy **Invoker**
        ```sh
        cd live/invoker
        terragrunt plan; terragrunt apply -auto-approve
        ```

### Step 3: Complete Slack app setup

- Return to api.slack.com/apps; you now have the API Gateway URL gotten from the output of the **slack_handler**
- In the Slack app left sideba: Event Subscriptions → toggle Enable Events → On
- In the Request URL field paste the api_endpoint output from **slack_handler**
- Slack immediately sends a url_verification challenge. The slack_handler Lambda returns the challenge automatically. After 2-3 seconds, Slack shows a green Verified checkmark
- Scroll down and Subscribe to bot events
- Add Bot User Event
    1. app_mention
    2. message.channels
- Click Save Changes. Reinstall the app when prompted (this is required after adding event subscriptions)
- Invite the bot a channel
    1. In your Slack workspace, open the channel you want to use. Type:
            * `/invite @agentcore-bot` 

### Step 4: Trigger the Runtime from Slack

Use any of these prompts:

- @agentcore-pe reate a bug in DEVOPS: "Login page crash on Safari"
- @agentcore-pe Create a Jira ticket in the DEVOPS project with the summary "Test ticket from AgentCore" and description "Testing the AgentCore Gateway Jira integration end to end" as a Task with Medium priority.
- @agentcore-pe create an S3 bucket in prod for verizon-users in the remote-work repo. Call it vrzn-use1-platform. Set the priority to High
