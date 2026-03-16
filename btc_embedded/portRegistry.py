import os, time, csv, subprocess, logging

lockLocation = os.environ['APPDATA'].replace('\\', '/') + "/BTC/restPortReg.lock"
portReg  = os.environ['APPDATA'].replace('\\', '/') + "/BTC/restPortReg.csv"
LOCK_MAX_LIFESPAN = 30
logger = logging.getLogger('btc_embedded')

def reservePortRegLock():
    #print("bb")
    while os.path.isfile(lockLocation):
        logger.debug("Waiting on port registry lock")
        #print(time.time() - os.path.getmtime(lockLocation))
        try:
            #Force delete lock as a back-up
            if time.time() - os.path.getmtime(lockLocation) > LOCK_MAX_LIFESPAN:
                os.remove(lockLocation)
        except:
            pass
        time.sleep(0.5)
    try:
        #x should return an exception if the file is already created. In case of EPs started at extremely similar times.
        with open(lockLocation,"x") as f:
            logger.debug("Port registry lock acquired")
            return True
    except:
        #Recursion should be alright as the lock will be force-deleted if it is too old.
        reservePortRegLock()

def clearPortRegLock():
    if os.path.isfile(lockLocation):
        os.remove(lockLocation)


def readPortReg():
    portInfos = []
    with open(portReg,"r") as f:
        regReader = csv.reader(f)
        for row in regReader:
            if not row == []:
                portInfos.append(row)
    return portInfos

def removeOutdatedRegs(portInfos):
    #startTime = time.time()
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE

    runningProcesses = subprocess.check_output('tasklist', startupinfo=startupinfo).decode().replace(" ","")
    updatedRegistrations = [[reg[0],reg[1]] for reg in portInfos if "ep.exe"+reg[0] in runningProcesses]

    with open(portReg, 'w',newline='') as f:
        portRegWriter = csv.writer(f)
        portRegWriter.writerows(updatedRegistrations)
    #print("removing outdated took", time.time()-startTime)
    return updatedRegistrations

def createPortReg():
    if not os.path.isfile(portReg):
        with open(portReg,"x"):
            pass


def startPortReg():
    createPortReg()
    portInfos = readPortReg()
    portInfos = removeOutdatedRegs(portInfos)
    return portInfos

def appendPortReg(pid,port):
    with open(portReg,'a') as f:
        f.write(str(pid) +","+str(port) + os.linesep)