import RPi.GPIO as GPIO
import time
import json
# Pin Definitons:
but_pin_1u = 16  # BOARD pin 16
but_pin_1d = 18  # BOARD pin 18
but_pin_2u = 24  # BOARD pin 24
but_pin_2d = 26  # BOARD pin 26


# Define function to update data and save to file
def update_data():
    data["type"] = type_var.get()
    data["number1"] = int(number1_var.get())
    data["number2"] = int(number2_var.get())
    with open("region_setting.json", "w") as f:
        json.dump(data, f)

def main():

    # Pin Setup:
    GPIO.setmode(GPIO.BOARD)  # BOARD pin-numbering scheme
    #GPIO.setup(led_pin, GPIO.OUT)  # LED pin set as output
    GPIO.setup(but_pin_1u, GPIO.IN)  # Button pin set as input
    GPIO.setup(but_pin_1d, GPIO.IN)  # Button pin set as input
    GPIO.setup(but_pin_2u, GPIO.IN)  # Button pin set as input
    GPIO.setup(but_pin_2d, GPIO.IN)  # Button pin set as input

    print("Starting demo now! Press CTRL+C to exit")
    try:
        while True:
            curr_1_up = GPIO.input(but_pin_1u)
            curr_1_down = GPIO.input(but_pin_1d)
            curr_2_up = GPIO.input(but_pin_2u)
            curr_2_down = GPIO.input(but_pin_2d)
            # DOOR 1 UP
            if (curr_1_up != 0):
                # Read data from file
                with open("region_setting.json", "r") as f:
                    data = json.load(f)
                data["number1"] = data["number1"]+1
                with open("region_setting.json", "w") as f:
                    json.dump(data, f)

            # DOOR 1 DOWN
            if (curr_1_down != 0):
                # Read data from file
                with open("region_setting.json", "r") as f:
                    data = json.load(f)
                data["number1"] = data["number1"]-1
                with open("region_setting.json", "w") as f:
                    json.dump(data, f)

            # DOOR 2 UP
            if (curr_2_up != 0):
                # Read data from file
                with open("region_setting.json", "r") as f:
                    data = json.load(f)
                data["number2"] = data["number2"]+1
                with open("region_setting.json", "w") as f:
                    json.dump(data, f)

            # DOOR 2 DOWN
            if (curr_2_down != 0):
                # Read data from file
                with open("region_setting.json", "r") as f:
                    data = json.load(f)
                data["number2"] = data["number2"]-1
                with open("region_setting.json", "w") as f:
                    json.dump(data, f)


            time.sleep(1)
    finally:
        GPIO.cleanup()  # cleanup all GPIO

if __name__ == '__main__':
    main()


