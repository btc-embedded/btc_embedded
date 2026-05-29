import os, time, csv, subprocess, logging

APPDATA = os.environ.get('APPDATA')
lockLocation = (APPDATA.replace('\\', '/') + "/BTC/restPortReg.lock") if APPDATA else None
portReg  = (APPDATA.replace('\\', '/') + "/BTC/restPortReg.csv") if APPDATA else None
LOCK_MAX_LIFESPAN = 30
LOCK_MAX_WAIT_SECONDS = 60
logger = logging.getLogger('btc_embedded')


def _ensure_windows():
    if not APPDATA:
        raise RuntimeError("portRegistry is only supported on Windows environments (APPDATA not set).")


def reservePortRegLock():
    ensurePortRegDir()
    start_time = time.time()
    while True:
        if time.time() - start_time > LOCK_MAX_WAIT_SECONDS:
            raise TimeoutError(f"Timed out waiting for port registry lock at '{lockLocation}'.")

        if os.path.isfile(lockLocation):
            logger.debug("Waiting on port registry lock")
            try:
                # Force delete stale lock as a back-up.
                if time.time() - os.path.getmtime(lockLocation) > LOCK_MAX_LIFESPAN:
                    os.remove(lockLocation)
                    logger.warning("Removed stale port registry lock file.")
            except FileNotFoundError:
                pass
            except OSError as e:
                logger.warning(f"Could not inspect or remove lock file '{lockLocation}': {e}")
            time.sleep(0.5)
            continue

        try:
            # x should return an exception if the file is already created.
            with open(lockLocation, "x"):
                logger.debug("Port registry lock acquired")
                return True
        except FileExistsError:
            # Another process acquired the lock between check and create.
            time.sleep(0.1)
        except OSError as e:
            logger.error(f"Failed to acquire port registry lock '{lockLocation}': {e}")
            raise

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
    _ensure_windows()
    os.makedirs(os.path.dirname(lockLocation), exist_ok=True)
