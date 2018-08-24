#!/usr/bin/env python3
import dialog
import subprocess
import os
import time
import sys
import socket
 
mechanicalWipeType = "zero"
webhook_url = 'https://hooks.slack.com/services/$$$$/$$$$' #Edit me
 
serviceTag = ((subprocess.Popen(['dmidecode','-s','system-serial-number'],stdout=subprocess.PIPE)).stdout.readline())[:-1]
model = ((subprocess.Popen(['dmidecode','-s','system-product-name'],stdout=subprocess.PIPE)).stdout.readline())[:-1]
logContents = "Service Tag : "+(serviceTag.decode('ascii'))+"\r\n"  # type: str
 
localDialog = dialog.Dialog(dialog="dialog",autowidgetsize=True)
localDialog.set_background_title("Drive Wipe")
 
#Disable screen blanking
subprocess.call(["setterm","-blank","0","-powerdown","0",])
 
#Wait a bit  for network to come up
localDialog.pause('Giving network time to connect',10,40,10)
 
 
#Check for network, if there isn't any : warn the user that it will not be able to log out
hasNetwork = False
continueWipe = False
completion = "successfully"
 
#Check if we can resolve slack for writing out our logs
slackIP = ''
slackIP = socket.gethostbyname('slack.com')
if not slackIP == '' :
    hasNetwork = True
 
 
#ask the user if we should continue without a default route and the ability to log
if not hasNetwork :
    if localDialog.yesno("Looks like we don't have network connectivity. \nI will not be able to automatically write out a log.\n\nWould you like to continue?", height=10, width=40) == localDialog.OK:
        continueWipe = True
    else:
        continueWipe = False
        localDialog.msgbox("\Z1\ZbNo network.\n I will shutdown now\Zn",colors='true')
        subprocess.call("poweroff", shell=True)
 
 
#Scan each disk, if there is an SSD ask to go to sleep
SSDAttached = False
MechanicalAttached = False
driveCount = 0
for entry in os.scandir("/sys/block/") :
    if not entry.name.startswith("loop") and not entry.name.startswith("sr") and not entry.name.startswith("fd"):
        driveCount = driveCount+1
        try:
            f=open(entry.path+"/queue/rotational","r")
            if f.readline().startswith("0") :
                print(entry.name+" is an ssd")
                SSDAttached = True
            else:
                MechanicalAttached = True
            f.close()
        except:
            print("Unexpected error:", sys.exc_info()[0])
 
#If we have an SSD we need to go to sleep/S3 to unlock it usually
if SSDAttached :
    localDialog.msgbox("An SSD was found, I will go to sleep to unlock the SSD.\r\n\nPush the power button to turn me back on once I am asleep - about 4 seconds.")
    subprocess.call('pm-suspend')
    localDialog.pause("Waiting for disks to settle",None,None,5)
    
 
#For each SSD secure erase to NULL, then a password, then back to NULL
for entry in os.scandir("/sys/block/") :
    if not entry.name.startswith("loop") and not entry.name.startswith("sr") and not entry.name.startswith("fd"):
        localDialog.gauge_start("Wiping /dev/"+entry.name+"", 15,45)
        wiped = ""
        try:
            if entry.name.startswith("nvm") :
                #NVMe - We use the NVMe commands
                localDialog.gauge_update(10,"Wiping /dev/"+entry.name+" with NVMe format with SES enabled.",True)
                print("Wiping /dev/"+entry.name+" with NVMe format with SES enabled")
                nvmewipe = subprocess.call(["nvme","format",("/dev/"+entry.name),"-s","1"])
                if nvmewipe == 0:
                    wiped = "NVMe User Data Wipe"
                else:
                    localDialog.gauge_update(10,"Wiping /dev/"+entry.name+" with NVMe format with SES enabled for Crypto keys only",True)
                    nvmewipe = subprocess.call(["nvme","format",("/dev/"+entry.name),"-s","2"])
                    if nvmewipe == 0:
                        wiped = "NVMe Crypto Keys Wipe"
            else:
                f=open(entry.path+"/queue/rotational","r")
                RotType = (f.readline())  # type: str
                f.close()
                if RotType.startswith("0") :
                    #SSD - Send a secure erase
                    localDialog.gauge_update(10,"Wiping /dev/"+entry.name+" with Secure Erase",True)
                    time.sleep(1)
                    subprocess.call(["hdparm","--user-master","u","--security-set-pass","NULL",("/dev/"+entry.name)])
                    time.sleep(1)
                    subprocess.call(["hdparm","--user-master","u","--security-set-pass","pass",("/dev/"+entry.name)])
                    time.sleep(1)
                    erase = subprocess.call(["hdparm","--user-master","u","--security-erase","pass",("/dev/"+entry.name)])
                    if erase == 0:
                        wiped = "SSD Secure Erase"
                    time.sleep(1)
                    subprocess.call(["hdparm","--security-disable","pass",("/dev/"+entry.name)])
                    time.sleep(1)
                else:
                    #Mechanical - Write zeros
                    localDialog.gauge_stop()
                    print("Wiping /dev/"+entry.name+" with shred")
                    shred = subprocess.call(["shred","-n 1","--verbose",("/dev/"+entry.name)])
                    if shred == 0 :
                        wiped = "shred"
                    localDialog.gauge_start("Wiping /dev/"+entry.name+"", 15,45)
 
        except:
            print("Unexpected error:", sys.exc_info()[0])
        localDialog.gauge_stop()
        if wiped == "" :
            logContents = logContents + "\r\nFailed Wipe for "+entry.path
            completion = "unsuccessfully."
        else :
            logContents = logContents + "\r\nWiped "+entry.path+" with "+wiped
 
#Log file out to slack 
import json
import requests
 
slack_data = {'text': "Wipe of "+(serviceTag.decode('ascii'))+" ["+(model.decode('ascii'))+"] completed "+completion+".","attachments": [
        {
            "title": "Wipe Completed",
            "text": logContents,
        }
    ]}
 
response = requests.post(
    webhook_url, data=json.dumps(slack_data),
    headers={'Content-Type': 'application/json'}
)
 
#Display log locally
localDialog.msgbox(logContents)
 
#Shutdown
subprocess.call("poweroff", shell=True)
