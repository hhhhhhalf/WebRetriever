
def transform(actions):
  string = ""
  for action in actions:
    cell_string = action["action_type"]
    if action["action_type"] == "MOVE_TO" or action["action_type"] == "DRAG_TO":
      x = action["parameters"]["x"]
      y = action["parameters"]["y"]
      cell_string += "(" + f"{x}"+ ", " + f"{y}" + ")"
      
    elif action["action_type"] == "CLICK":
      x = action["parameters"]["x"]
      y = action["parameters"]["y"]
      cell_string += "(" + f"{x}"+ ", " + f"{y}" + ")"
      if action["parameters"]["button"] == "left":
        cell_string += "{button: LEFT, "
      elif action["parameters"]["button"] == "right":
        cell_string += "{button: RIGHT, "
      num_clicks = action["parameters"]["num_clicks"]
      cell_string += "num_clicks: " + f"{num_clicks}" + "}"

    elif action["action_type"] == "SCROLL":
      if action["parameters"]["y"] > 0:
        cell_string += "_UP"
      elif action["parameters"]["y"] < 0:
        cell_string += "_DOWN"
    elif action["action_type"] == "PRESS":
        cell_string += "(" + action["parameters"]["key"] + ")"
    elif action["action_type"] == "MOUSE_DOWN":
      cell_string += "{button: " + action["parameters"]["button"] + "}"
    
    if action != actions[-1]:
      cell_string += " -> "
  string += cell_string
  return string