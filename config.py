import adsk.core
import os
import os.path
import json
from .lib import fusionAddInUtils as futil

# Global Variables
DEBUG = True
# ADDIN_NAME is derived from the directory name of the current file
ADDIN_NAME = os.path.basename(os.path.dirname(__file__))
ADDIN_NAME = os.path.basename(os.path.dirname(__file__))
COMPANY_NAME = "IMA LLC"

# Unique identifier for the sample palette
sample_palette_id = f"{COMPANY_NAME}_{ADDIN_NAME}_palette_id"
sample_palette_id = f"{COMPANY_NAME}_{ADDIN_NAME}_palette_id"

design_workspace = "FusionSolidEnvironment"
tools_tab_id = "ToolsTab"
my_tab_name = "Power Tools"

my_panel_id = f"{ADDIN_NAME}_panel_2"
my_panel_name = "Tools"
my_panel_after = ""