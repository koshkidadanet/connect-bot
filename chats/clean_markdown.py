import re
import os

def clean_markdown(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()

    # Remove all Python code blocks
    cleaned_content = re.sub(r'```[\s\S]*?```', '', content)

    # Create new file path
    directory, filename = os.path.split(file_path)
    new_filename = f"cleaned_{filename}"
    new_file_path = os.path.join(directory, new_filename)

    with open(new_file_path, 'w', encoding='utf-8') as file:
        file.write(cleaned_content)


clean_markdown('D:\education\itmo\ponl\connect-bot\chats\sprint_2.1.md')