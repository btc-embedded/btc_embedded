import os, time, csv, subprocess, logging

lockLocation = os.environ['APPDATA'].replace('\\', '/') + "/BTC/restPortReg.lock"
portReg  = os.environ['APPDATA'].replace('\\', '/') + "/BTC/restPortReg.csv"
LOCK_MAX_LIFESPAN = 30
logger = logging.getLogger('btc_embedded')


def reservePortRegLock():
    ensurePortRegDir()
    while os.path.isfile(lockLocation):
        logger.debug("Waiting on port registry lock")
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
        # protects against the extremely unlikely case of two EPs starting at the exact same time and both passing the initial check for the lock file, then both trying to create it at the same time. Only one will succeed, the other will get an exception and wait for the next loop to acquire the lock.
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
    ensurePortRegDir()
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE

    runningProcesses = subprocess.check_output('tasklist', startupinfo=startupinfo).decode().replace(" ","")
    updatedRegistrations = [[reg[0],reg[1]] for reg in portInfos if "ep.exe"+reg[0] in runningProcesses]

    with open(portReg, 'w',newline='') as f:
        portRegWriter = csv.writer(f)
        portRegWriter.writerows(updatedRegistrations)
    return updatedRegistrations

def createPortReg():
    ensurePortRegDir()
    if not os.path.isfile(portReg):
        with open(portReg,"x"):
            pass


def startPortReg():
    createPortReg()
    portInfos = readPortReg()
    portInfos = removeOutdatedRegs(portInfos)
    return portInfos

def appendPortReg(pid,port):
    ensurePortRegDir()
    with open(portReg,'a') as f:
        f.write(str(pid) +","+str(port) + os.linesep)

def ensurePortRegDir():
    os.makedirs(os.path.dirname(lockLocation), exist_ok=True)
