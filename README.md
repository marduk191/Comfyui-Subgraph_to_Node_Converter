# Comfyui-Subgraph_to_Node_Converter


ComfyUI Subgraph → Node Converter
A single-file ComfyUI custom node that converts any subgraph saved inside a workflow JSON into a real, installable Python custom node — without ever leaving ComfyUI.

Install
Drop comfyui_subgraph_to_node.py into ComfyUI/custom_nodes/ and restart.
No folder, no __init__.py, no pip installs required.

Find the node under: utils/subgraph → "Subgraph → Node Converter"

Quick Start
In ComfyUI, build your subgraph and save the workflow as .json into ComfyUI/input/

Add the Subgraph → Node Converter node to any workflow

Select your file from the json_file dropdown

Fill in naming fields (or leave blank to use the subgraph name)

Set dry_run = True and connect generated_code → Show Text to preview

Flip dry_run = False and queue — files are written

Restart ComfyUI — your new node appears in the category you chose

Sockets:
<img width="729" height="638" alt="image" src="https://github.com/user-attachments/assets/0b7c18c5-d576-418d-ab37-049b2b04e366" />
<img width="719" height="182" alt="image" src="https://github.com/user-attachments/assets/e835d818-18d8-4e6c-be82-430d35eaf5bf" />

Namning fields cheatsheet:
subgraph name  →  "My KSampler Pipe"      (from the workflow JSON)

node_name      →  "MyKSamplerPipe"        NODE_CLASS_MAPPINGS key
display_name   →  "My KSampler Pipe"      Add-Node menu label
category       →  "sampling/pipes"        menu location
class_name     →  "MyKSamplerPipeNode"    Python class name in .py
All four fall back gracefully if left blank. The status output always echoes the resolved values so you know exactly what was used.

Supported Subgraph Formats
Format	Storage location	ComfyUI version
New subgraph	workflow["definitions"]["subgraphs"]	≥ Aug 2025
Legacy group node	workflow["extra"]["groupNodes"]	< Aug 2025
Bare subgraph file	The JSON file itself is the subgraph	any
Generated Output
Every run writes two files into output_directory:

File	Description
File	Description
<snake_node_name>_node.py	The custom node class
__init__.py	Package registration — re-scans all *_node.py files so multiple subgraphs can share the same output folder
Converting multiple subgraphs? Just point them all at the same output_directory. The __init__.py is regenerated each time and picks up every node in the folder.

After Converting
Make sure output_directory is inside (or symlinked into) ComfyUI/custom_nodes/

Restart ComfyUI

Your new node appears under the category you set

All internal nodes of the subgraph must already be installed — the generated node calls them at runtime via NODE_CLASS_MAPPINGS

Notes & Caveats
Hardcoded widget values baked into the subgraph are embedded as defaults in the generated node. Review them after generation.

Reroute / Note nodes inside the subgraph are skipped — they aren't executable node types.

The file picker (json_file dropdown) uses IS_CHANGED hashing and refreshes automatically whenever .json files are added to or removed from ComfyUI/input/.

The path_override field accepts ~ and environment variables (e.g. %USERPROFILE%\workflows\my_flow.json).
