# WhatsApp
import subprocess
import time

import win32com.client as comclt


def WhatsApp_Send(StrTxt):
    StrTxt = StrTxt.replace(" ", "%20")

    wsh = comclt.Dispatch("WScript.Shell")
    wsh.AppActivate("WhatsApp")  # select another application
    time.sleep(5)

    p = subprocess.Popen(
        ["cmd", "/C", "start whatsapp://send?phone=+447384545771^&text=" + StrTxt],
        shell=True,
    )

    time.sleep(10)
    wsh.AppActivate("WhatsApp")  # select another application
    time.sleep(1)
    wsh.SendKeys("{ENTER}")  # send the keys you want


# from selenium import webdriver
# from selenium.webdriver.support.ui import WebDriverWait
# from selenium.webdriver.support import expected_conditions as EC
# from selenium.webdriver.common.keys import Keys
# from selenium.webdriver.common.by import By
# import time
#
## Replace below path with the absolute path
## to chromedriver in your computer
# driver = webdriver.Chrome('C:\Users\Jason\OneDrive\Documents\Python Files')
#
# driver.get("https://web.whatsapp.com/")
# wait = WebDriverWait(driver, 600)
#
## Replace 'Friend's Name' with the name of your friend
## or the name of a group
# target = '"Friend\'s Name"'
#
## Replace the below string with your own message
# string = "Message sent using Python!!!"
#
# x_arg = '//span[contains(@title,' + target + ')]'
# group_title = wait.until(EC.presence_of_element_located((
#    By.XPATH, x_arg)))
# group_title.click()
# inp_xpath = '//div[@class="_13NKt copyable-text selectable-text"][@data-tab="9"]'
# input_box = wait.until(EC.presence_of_element_located((
#    By.XPATH, inp_xpath)))
# for i in range(100):
#    input_box.send_keys(string + Keys.ENTER)
#    time.sleep(1)
