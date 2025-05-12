import os
import sys
import json
import requests

def main():
    new_tag = os.environ.get("INPUT_NEW_TAG")
    notes_with_real_newlines = os.environ.get("INPUT_RELEASE_NOTES") 
    github_token = os.environ.get("INPUT_GITHUB_TOKEN")
    github_repository = os.environ.get("INPUT_GITHUB_REPOSITORY") 

    if not all([new_tag, notes_with_real_newlines, github_token, github_repository]):
        print("Error: Missing one or more required environment variables.")
        print(f"NEW_TAG: {new_tag is not None}")
        print(f"RELEASE_NOTES: {notes_with_real_newlines is not None}")
        print(f"GITHUB_TOKEN: {github_token is not None}")
        print(f"GITHUB_REPOSITORY: {github_repository is not None}")
        sys.exit(1)

    api_url = f"https://api.github.com/repos/{github_repository}/releases"

    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json", 
    }

    escaped_notes_for_json_value = notes_with_real_newlines.replace('\\', '\\\\').replace('"', '\\"')
    

    manual_payload_str = f'''{{
        "tag_name": "{new_tag}",
        "name": "Release {new_tag}",
        "body": "{escaped_notes_for_json_value}",
        "draft": false,
        "prerelease": false
    }}'''

    print(f"Creating release {new_tag} for repository {github_repository} via API...")
    print(f"API URL: {api_url}")
    print(f"Manually constructed Payload string being sent (notes might be long):\n{manual_payload_str}\n")

    try:
        response = requests.post(api_url, headers=headers, data=manual_payload_str.encode('utf-8'), timeout=30)
        response.raise_for_status() 
        
        response_data = response.json()
        print(f"✅ GitHub Release for {new_tag} created successfully!")
        print(f"Release URL: {response_data.get('html_url')}")
        print(f"API Response (HTTP {response.status_code}):\n{json.dumps(response_data, indent=2)}")

    except requests.exceptions.HTTPError as http_err:
        print(f"❌ HTTP error occurred: {http_err}")
        print(f"Response content:\n{http_err.response.text}")
        sys.exit(1)
    except requests.exceptions.RequestException as req_err:
        print(f"❌ Request error occurred: {req_err}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ An unexpected error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 