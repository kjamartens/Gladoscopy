from MainScripts import FunctionHandling

# Required function __function_metadata__
# Should have an entry for every function in this file
def __function_metadata__():
    return {
        "CellArea_lowerUpperBound": {
            "required_kwargs": [
                {"name": "outline_coords", "description": "List of outline coordinates belonging to individual cells."},
                {"name": "size_bounds", "description": "[lower, upper] bounds in pixel units"}
            ],
            "optional_kwargs": [
            ],
            "help_string": "Score cells 1 or 0 based on whether they are within area lower/upper bounds."
        }
    }

def CellArea_lowerUpperBound(**kwargs):
    return 1