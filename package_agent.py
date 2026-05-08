import os
import zipfile

def zip_folder(folder_path, output_path):
    # Folders and files to exclude
    exclude = {'venv', '__pycache__', 'agent_config.json', '.git', '.venv', 'PrintHub_Agent.zip'}
    
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(folder_path):
            # Remove excluded directories from search
            dirs[:] = [d for d in dirs if d not in exclude]
            
            for file in files:
                if file.endswith(('.pyc', '.pyo')):
                    continue
                if file in exclude:
                    continue
                    
                file_path = os.path.join(root, file)
                # Create the path inside the zip (relative to the agent folder)
                arcname = os.path.relpath(file_path, folder_path)
                zipf.write(file_path, arcname)

if __name__ == "__main__":
    agent_dir = "agent"
    output_zip = "PrintHub_Agent.zip"
    print(f"Creating {output_zip} from {agent_dir}...")
    zip_folder(agent_dir, output_zip)
    print("Done! You can now send PrintHub_Agent.zip to other laptops.")

