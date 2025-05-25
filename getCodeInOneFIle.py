import os

def concatenate_folder_contents(input_folder, output_file):
    with open(output_file, 'w', encoding='utf-8') as outfile:
        for root, dirs, files in os.walk(input_folder):
            for filename in files:
                file_path = os.path.join(root, filename)
                rel_path = os.path.relpath(file_path, input_folder)
                
                # Write header with folder and file path
                outfile.write(f"\n\n--- Start of file: {rel_path} ---\n")
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as infile:
                        content = infile.read()
                        outfile.write(content)
                except Exception as e:
                    outfile.write(f"[Error reading file: {e}]")
                
                outfile.write(f"\n--- End of file: {rel_path} ---\n")

# Example usage
input_folder = 'D:\\Projects\\filepilot\\code'
output_file = 'D:\\Projects\\filepilot\\combined_output.txt'
concatenate_folder_contents(input_folder, output_file)
