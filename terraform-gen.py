import os
import shutil
import git
import requests
import subprocess
import sys
import json
import openai

# Configuration
REPO_URL = 'https://github.com/username/project-repo.git'
BASE_BRANCH_NAME = 'aidemo'
NEW_BRANCH_NAME = 'RITM0011'
FOLDER_TO_DUPLICATE = 'templates'
GITHUB_TOKEN = os.environ['PAT']
GITHUB_REPO = 'innersource-nn/project-repo'
LOCAL_PATH = '/tmp/project-repo'
USERNAME = 'WOAE_nngithub'
TARGET_ACCOUNT = sys.argv[1]
INPUT_FILE_PATH = 'templates/vm.tf'
OUTPUT_FILE_PATH = '{}/{}/main.tf'.format(LOCAL_PATH, NEW_BRANCH_NAME)
LOCAL_BRANCH_PATH = '{}/{}'.format(LOCAL_PATH, NEW_BRANCH_NAME)

###################### """
# pip3 install openai==0.28 gitpython requests
# export OPENAI_API_KEY=sk-xxxx
# export PAT=ghp_xxxx
# Also export AWS credentials or use AWS CLI configured
###################### """

def setup_repo(REPO_URL, LOCAL_PATH, USERNAME, GITHUB_TOKEN):
    if not os.path.exists(LOCAL_PATH):
        print("Cloning the repository...")
        repo = git.Repo.clone_from(
            REPO_URL.replace('https://', f'https://{USERNAME}:{GITHUB_TOKEN}@'),
            LOCAL_PATH,
            branch=BASE_BRANCH_NAME
        )
    else:
        repo = git.Repo(LOCAL_PATH)
    return repo

def run_terraform(repo, command):
    os.chdir(LOCAL_BRANCH_PATH)
    try:
        # Execute the command
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True  # Ensure text mode for outputs
        )

        # Wait for the command to complete
        stdout, stderr = process.communicate()

        if process.returncode != 0:
            print(f"Error: {stderr}")
            return stderr
        else:
            print(f"Success: {stdout}")
            tfsec_out = ''
            if 'tfsec' in command:
                tfsec_out = f"## Terraform Security\n```html\n{stdout}\n```"
            if 'plan' in command:
                create_pull_request(repo, stdout+tfsec_out)
            return stdout
    except Exception as e:
        print(f"An exception occurred: {str(e)}")
        return str(e)

def read_terraform_file(file_path):
    with open(file_path, 'r') as file:
        return file.read()

def write_terraform_file(file_path, content):
    if not os.path.exists(LOCAL_BRANCH_PATH):
        os.chdir(LOCAL_PATH)
        shutil.copytree(FOLDER_TO_DUPLICATE, f'{NEW_BRANCH_NAME}')
        os.chdir(f"{LOCAL_PATH}/{NEW_BRANCH_NAME}")
    if os.path.exists(f"{LOCAL_PATH}/{NEW_BRANCH_NAME}/vm.tf"):
        os.remove(f"{LOCAL_PATH}/{NEW_BRANCH_NAME}/vm.tf")
    with open(file_path, 'w') as file:
        file.write(content)

def generate_ec2_instance_code(user_input, basic_code):
    prompt = """
    DO NOT INCLUDE ANY EXPLANATIONS OR NOTES OR INFORMATION, JUST CODE BLOCK. TO {} in AWS by Updating terraform template code {} as following
    1. missing variables are provided separately while running terraform plan.
    2. No Public IP
    3. No root_block device. Will come from AMI size
    3. disk encryption also comes from AMI
    4. No owner for AMI
    5. Add Provider with region eu-central-1
    6. Tags with Project=project-repo
    7. Instance type t2.micro if size not mentioned
    8. Data volume size 80GB if size not mentioned
    9. Attach data volume to /dev/sdf to the instance
    10. Attach instance profile 'SecretEC2Role-eu-central-1'
    11. Do NOT remove anything in current terraform template code provided
    DO NOT INCLUDE ANY EXPLANATIONS OR NOTES OR INFORMATION, JUST CODE BLOCK.
    """.format(user_input, basic_code)

    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a AWS cloud infrastructure engineer."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.4
    )
    # TODO find a better solution for this
    new_string = response.choices[0].message['content'].strip().replace("```hcl", "")
    cleaned_output = new_string.replace("```", "").replace("```terraform", "")
    return cleaned_output

def create_pull_request(repo, plan_output):
    # Git commit
    # Create new branch
    os.chdir(LOCAL_PATH)
    repo.git.checkout('-b', NEW_BRANCH_NAME)
    repo.git.add(A=True)
    repo.git.commit(m=f'NEW TF for request {NEW_BRANCH_NAME}')
    # Push changes to new branch
    repo.git.push('--set-upstream', 'origin', NEW_BRANCH_NAME)
    url = f"https://api.github.com/repos/{GITHUB_REPO}/pulls"
    PR_BODY = f"## Terraform Plan Output\n```hcl\n{plan_output}\n```"
    PR_TITLE = f'TF plan for {NEW_BRANCH_NAME}'

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }

    data = {
        "title": PR_TITLE,
        "head": NEW_BRANCH_NAME,
        "base": BASE_BRANCH_NAME,
        "body": PR_BODY
    }

    response = requests.post(url, headers=headers, data=json.dumps(data))

    if response.status_code == 201:
        print("Pull request created successfully.")
        print("Pull request URL:", response.json().get('html_url'))
    else:
        print("Failed to create pull request.")
        print("Response:", response.json())

if __name__ == "__main__":
    openai.api_key = os.getenv("OPENAI_API_KEY")
    if not openai.api_key:
        raise ValueError("OpenAI API key not set. Please set the OPENAI_API_KEY environment variable.")
    create_instance = input("What you want to create? \n")

    # Setup repo and create a dummy file
    repo = setup_repo(REPO_URL, LOCAL_PATH, USERNAME, GITHUB_TOKEN)

    print("Generating New Terraform'...")

    # Read the basic Terraform content from the file
    basic_terraform_content = read_terraform_file(f"{LOCAL_PATH}/{INPUT_FILE_PATH}")

    ec2_instance_code = generate_ec2_instance_code(create_instance, basic_terraform_content)
    updated_content = ec2_instance_code

    # Write the updated content back to a new Terraform file
    write_terraform_file(OUTPUT_FILE_PATH, updated_content)

    # Run 'terraform init'
    print("Running 'Terraform init'...")
    init_result = run_terraform(repo, ['terraform', 'init'])

    # Run 'terraform Validate'
    print("Running 'Terraform Validate'...")
    init_result = run_terraform(repo, ['terraform', 'validate'])

    # Run 'terraform Security Check'
    print("Running 'Terraform Security Check'...")
    init_result = run_terraform(repo, ['tfsec', './', '--format=html'])

    # Run 'terraform plan' and output to a file
    print("Running 'Terraform plan'...")
    plan_result = run_terraform(repo, ['terraform', 'plan', '-var', f'target_account_name={TARGET_ACCOUNT}' , '--out=plan.out'])