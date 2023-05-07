import tkinter as tk
import json

# Read data from file
with open("region_setting.json", "r") as f:
    data = json.load(f)

# Define function to update data and save to file
def update_data():
    data["type"] = type_var.get()
    data["number1"] = int(number1_var.get())
    data["number2"] = int(number2_var.get())
    with open("region_setting.json", "w") as f:
        json.dump(data, f)

# Create main window
root = tk.Tk()

# Create widgets
root.title("Settings")
root.geometry("200x200")
type_label = tk.Label(root, text="Enter Type:")
type_options = ["both", "upper", "under", "close"]
type_var = tk.StringVar(value=data["type"])
type_menu = tk.OptionMenu(root, type_var, *type_options)

number1_label = tk.Label(root, text="Number 1:")
number1_var = tk.StringVar(value=str(data["number1"]))
number1_entry = tk.Entry(root, textvariable=number1_var)

number2_label = tk.Label(root, text="Number 2:")
number2_var = tk.StringVar(value=str(data["number2"]))
number2_entry = tk.Entry(root, textvariable=number2_var)

save_button = tk.Button(root, text="Save", command=update_data)

# Pack widgets
type_label.pack()
type_menu.pack()
number1_label.pack()
number1_entry.pack()
number2_label.pack()
number2_entry.pack()
save_button.pack()

# Start main loop
root.mainloop()

