import serial
import time
import sys
tgsCom    = 'COM12'
tgS = serial.Serial()
tgS.port = tgsCom
tgS.baudrate = 115200
tgS.bytesize = serial.EIGHTBITS #number of bits per bytes
tgS.parity = serial.PARITY_NONE #set parity check: no parity
tgS.stopbits = serial.STOPBITS_ONE #number of stop bits
#tgS.timeout = None          #block read
tgS.timeout = 0.5            #non-block read
tgS.xonxoff = False     #disable software flow control
tgS.rtscts = False     #disable hardware (RTS/CTS) flow control
tgS.dsrdtr = False       #disable hardware (DSR/DTR) flow control
tgS.writeTimeout = 0     #timeout for write


try:
    print("Activating Triggerscope...")
    tgS.open()
except Exception:
    print("ERROR: Triggerscope Com port NOT OPEN: ")
    exit()


def writetgs(tgin):
    '''send a serial command to the triggerscope...
    Args:
        tgin: input string to send. Note the command terminator should be included in the string.
    Returns:
        char string of whatever comes back on the serial line.
    Raises:
        none.
    '''
    tgS.flushInput() #flush input buffer, discarding all its contents
    tgS.flushOutput()#flush output buffer, aborting current output
    time.sleep(0.01)  #give the serial port sometime to receive the data 50ms works well...
    tgS.write(str.encode(tgin)) #send an ack to tgs to make sure it's up
    time.sleep(0.01)  #give the serial port sometime to receive the data 50ms works well...
    bufa = ""
    bufa = tgS.readline().decode()
    return bufa


def inputTS(text):
    a = writetgs(text)
    #time.sleep(0.1)
    print(a)

if tgS.isOpen():
    try:

        #Test connection
        inputTS('PAC1\n')
        inputTS('CLEAR_ALL\r\n')

        #Do everything in my power to clear earlier data
        print(writetgs('PAC1\r\n')) #CLEAR settings
        print(writetgs('PAO1-0-0\r\n')) #Set DAC1 to switch between 20000 and 0 Starting at sequence 0
        print(writetgs('PAO1-1-0\r\n')) #Set DAC1 to switch between 20000 and 0 Starting at sequence 0
        print(writetgs('BAD1-0\r\n')) #To set a 5 ms delay before turning on DAC1 after the start of the high TTL
        print(writetgs('BAL1-0\r\n')) #Laser on for only 10 ms
        print(writetgs('PAS1-1-1\r\n')) #Trigger transition at DAC 1 - starting (1 middle) on rising edge (1 end)
        print(writetgs('BAO1-1-0\n')) #Add the blanking mode - now it turns off when no high TTL is received

        print(writetgs('PAC2\r\n')) #CLEAR settings
        print(writetgs('PAO2-0-65535\r\n')) #Set DAC1 to switch between 20000 and 0 Starting at sequence 0
        print(writetgs('BAD2-0\r\n')) #To set a 5 ms delay before turning on DAC1 after the start of the high TTL
        print(writetgs('BAL2-0\r\n')) #Laser on for only 10 ms
        print(writetgs('PAS2-1-1\r\n')) #Trigger transition at DAC 1 - starting (1 middle) on rising edge (1 end)
        print(writetgs('BAO2-1-0\n')) #Add the blanking mode - now it turns off when no high TTL is received

        print(writetgs('PAC4\r\n')) #CLEAR settings
        print(writetgs('PAO4-0-65535\r\n')) #Set DAC1 to switch between 20000 and 0 Starting at sequence 0
        print(writetgs('BAD4-1\r\n')) #To set a 5 ms delay before turning on DAC1 after the start of the high TTL
        print(writetgs('BAL4-50000\r\n')) #Laser on for only 10 ms
        print(writetgs('PAS4-1-1\r\n')) #Trigger transition at DAC 1 - starting (1 middle) on rising edge (1 end)
        print(writetgs('BAO4-1-0\n')) #Add the blanking mode - now it turns off when no high TTL is received
        #time.sleep(5)

        #print(writetgs('CLEAR_ALL\r\n'))#Clear all
        #print(writetgs('PAC1\r\n')) #CLEAR settings
        #print(writetgs('PAC2\r\n')) #CLEAR settings
        #print(writetgs('PAC4\r\n')) #CLEAR settings
        #print(writetgs('PAC5\r\n')) #CLEAR settings

        time.sleep(0.1)
        #print(writetgs('PAO1-0-0\r\n')) #Set DAC1 to switch between 20000 and 0 Starting at sequence 0
        #print(writetgs('PAS1-1-1\r\n')) #Trigger transition at DAC 1 - starting (1 middle) on rising edge (1 end)
        #print(writetgs('BAO1-1-0\n')) #Add the blanking mode - now it turns off when no high TTL is received
        #print(writetgs('PAO2-0-65000\r\n')) #Set DAC1 to switch between 20000 and 0 Starting at sequence 0
        #print(writetgs('PAS2-1-1\r\n')) #Trigger transition at DAC 1 - starting (1 middle) on rising edge (1 end)
        #print(writetgs('BAO2-1-0\n')) #Add the blanking mode - now it turns off when no high TTL is received
        #print(writetgs('PAO4-0-65000\r\n')) #Set DAC1 to switch between 20000 and 0 Starting at sequence 0
        #print(writetgs('PAS4-1-1\r\n')) #Trigger transition at DAC 1 - starting (1 middle) on rising edge (1 end)
        #print(writetgs('BAO4-1-0\n')) #Add the blanking mode - now it turns off when no high TTL is received


        #print(writetgs('BAD1-0\r\n')) #To set a 100 ms delay before turning on DAC1 after the start of the high TTL
        #print(writetgs('BAL1-0\r\n')) #Laser on for only 100 ms
        #print(writetgs('BAD2-0\r\n')) #To set a 100 ms delay before turning on DAC1 after the start of the high TTL
        #print(writetgs('BAL2-0\r\n')) #Laser on for only 100 ms
        #print(writetgs('BAD4-0\r\n')) #To set a 100 ms delay before turning on DAC1 after the start of the high TTL
        #print(writetgs('BAL4-0\r\n')) #Laser on for only 100 ms
        """

        time.sleep(0.1)
        print(writetgs('PAO2-0-65535\r\n')) #Set DAC1 to switch between 20000 and 0 Starting at sequence 0
        print(writetgs('PAO2-1-0\r\n')) #Set DAC1 to switch between 20000 and 0 Starting at sequence 0

        print(writetgs('BAD2-5000\r\n')) #To set a 100 ms delay before turning on DAC1 after the start of the high TTL
        print(writetgs('BAL2-15000\r\n')) #Laser on for only 100 ms
        print(writetgs('PAS2-1-1\r\n')) #Trigger transition at DAC 1 - starting (1 middle) on rising edge (1 end)

        #Set blanking info
        print(writetgs('BAO2-1-0\n')) #Add the blanking mode - now it turns off when no high TTL is received


        print(writetgs('PAC4\r\n')) #CLEAR settings
        time.sleep(0.1)
        print(writetgs('PAO4-0-65535\r\n')) #Set DAC1 to switch between 20000 and 0 Starting at sequence 0
        print(writetgs('PAO4-1-0\r\n')) #Set DAC1 to switch between 20000 and 0 Starting at sequence 0

        print(writetgs('BAD4-5000\r\n')) #To set a 100 ms delay before turning on DAC1 after the start of the high TTL
        print(writetgs('BAL4-15000\r\n')) #Laser on for only 100 ms
        print(writetgs('PAS4-1-1\r\n')) #Trigger transition at DAC 1 - starting (1 middle) on rising edge (1 end)

        #Set blanking info
        print(writetgs('BAO4-1-0\n')) #Add the blanking mode - now it turns off when no high TTL is received


        print(writetgs('PAC5\r\n')) #CLEAR settings
        time.sleep(0.1)
        print(writetgs('PAO5-0-65535\r\n')) #Set DAC1 to switch between 20000 and 0 Starting at sequence 0
        print(writetgs('PAO5-1-0\r\n')) #Set DAC1 to switch between 20000 and 0 Starting at sequence 0

        print(writetgs('BAD5-5000\r\n')) #To set a 100 ms delay before turning on DAC1 after the start of the high TTL
        print(writetgs('BAL5-15000\r\n')) #Laser on for only 100 ms
        print(writetgs('PAS5-1-1\r\n')) #Trigger transition at DAC 1 - starting (1 middle) on rising edge (1 end)

        #Set blanking info
        print(writetgs('BAO5-1-0\n')) #Add the blanking mode - now it turns off when no high TTL is received
            """



        #time.sleep(5)
        #Set triggering info
        #print(writetgs('PAO1-0-65535\n')) #Set DAC1 to switch between 20000 and 0 Starting at sequence 0
        #print(writetgs('PAS1-1-0\n')) #Trigger transition at DAC 1 - starting (1 middle) on rising edge (1 end)

        #Set blanking info
        #print(writetgs('BAL1-100\n')) #Add length
        #print(writetgs('BAO1-1-0\n')) #Add the blanking mode - now it turns off when no high TTL is received
        #print(writetgs('SAO1-50000\n')) #Add the blanking mode - now it turns off when no high TTL is received
        """
        print(writetgs('CLEAR_ALL\n'))#Clear all
        print(writetgs('PDC0\n')) #Clear all
        print(writetgs('PDS1-0-1\n')) #Stop triggering
        #print(writetgs('BAO1-0-0\n')) #Stop blanking

        print(writetgs('PDO0-0-1\n')) #Set DAC1 to switch between 20000 and 0 Starting at sequence 0
        print(writetgs('PDS0-1-1\n')) #Set DAC1 to switch between 20000 and 0 Starting at sequence 0

        print(writetgs('BDO0-1-0\n')) #Add the blanking mode - now it turns off when no high TTL is received

        #print(writetgs('SDO0,1\n')) #Clear all
        #time.sleep(0.5)
        #print(writetgs('SDO0,0\n')) #Clear all

        #print(writetgs('BAL1-100000\n')) #Set max duration of pulse
        #print(writetgs('PAS1-1-1\n')) #Trigger transition at DAC 1 - starting (1 middle) on falling edge (0 end)


        #print(writetgs('*\n'))
        #print(writetgs('SAO1-20000\n'))
        #print(writetgs('SAO1-0\n'))
        """
        #"""
        #print(writetgs('RESET\n'))
        #print(writetgs('PAS1-0-0\n')) #Stop triggering
        #print(writetgs('BAO1-0-0\n'))
        """
        print(writetgs('CLEAR_ALL\n'))
        print(writetgs('RANGE1,1\n'))
        print(writetgs('TRIGMODE,1,2\n'))
        print(writetgs('PROG_DAC,1,1,20000\n'))
        print(writetgs('PROG_DAC,2,1,0\n'))
        print(writetgs('TIMECYCLES,5\n'))
        #print(writetgs('WAITTRIGGER,10000\n'))
        print(writetgs('ARM\n'))

        print(writetgs('*\n'))
        print(writetgs('*\n'))
        """


        """
        tgS.write(str.encode('PROG_DAC,1,1,20000\n'))
        time.sleep(0.2);
        print("Rx: " + tgS.readline().decode()) #Receive line
        tgS.write(str.encode('PROG_DAC,2,1,0\n'))
        time.sleep(0.2);
        print("Rx: " + tgS.readline().decode()) #Receive line
        tgS.write(str.encode('TIMECYCLES,5\n'))
        time.sleep(0.2);

        print("Rx: " + tgS.readline().decode()) #Receive line
        tgS.write(str.encode('ARM\n'))
        time.sleep(0.2);
        print("Rx: " + tgS.readline().decode()) #Receive line

        time.sleep(0.5)
        tgS.write(str.encode('*\n')) #send an ack to tgs to make sure it's up
        time.sleep(0.1)  #give the serial port sometime to receive the data
        print("Rx0: " + tgS.readline().decode()) #Receive line
        tgS.write(str.encode('*\n')) #send an ack to tgs to make sure it's up
        time.sleep(0.1)  #give the serial port sometime to receive the data
        print("Rx0: " + tgS.readline().decode()) #Receive line
        """
        """
        print("Rx: " + tgS.readline().decode()) #Receive line
        print("Rx: " + tgS.readline().decode()) #Receive line
        #tgS.write(str.encode('*\n')) #send an ack to tgs to make sure it's up
        #print("Rx: " + tgS.readline().decode()) #Receive line

        #tgS.flushInput() #flush input buffer, discarding all its contents
        #tgS.flushOutput()#flush output buffer, aborting current output

        #tgS.write(str.encode('CLEAR_ALL\n'))
        #tgS.write(str.encode('RANGE1,1\n'))


        #time.sleep(0.5)
        #tgS.write(str.encode('DAC1,0\n'))
        #time.sleep(0.1)
        #print("Rx1: " + tgS.readline().decode()) #Receive line


        #tgS.write(str.encode('DAC1,20000\n'))
        #writetgs('DAC1,0\n')
        print(writetgs('DAC1,20000\n'))
        time.sleep(0.5)
        print(writetgs('DAC1,0\n'))

        #time.sleep(0.1)
        #print("Rx2: " + tgS.readline().decode()) #Receive line
        #time.sleep(0.5)
        #tgS.write(str.encode('DAC1,0\n'))
        #time.sleep(0.1)
        #print("Rx3: " + tgS.readline().decode()) #Receive line

        #tgS.write(str.encode('*\n')) #send an ack to tgs to make sure it's up
        #time.sleep(0.1)  #give the serial port sometime to receive the data
        #print("Rx0: " + tgS.readline().decode()) #Receive line
        """
    except Exception:
        print("triggerscope serial communication error...: ")

else:
    print("cannot open triggerscope port ")


"""
def loadTgs():
    print "Loading prog array.."
    for i in range(10):
        sout = ("PROG_TTL,%d,8,1\n" % (i+1) ) #prog command for triggerscope
        writetgs(sout)
        print sout
        time.sleep(0.01)
    print"done."

def armTgs():
    sout = ("ARM\n") #prog command for triggerscope
    writetgs(sout)
    print sout

def progtest():
    print(writetgs("PROG_DAC,1,1,65000\n") )
    #print(writetgs("PROG_DAC,2,1,0\n") )

    print(writetgs("PROG_DAC,2,1,32000\n") )

    print(writetgs("PROG_TTL,1,1,1\n") )
    print(writetgs("PROG_TTL,2,2,1\n") )
    print(writetgs("ARM\n") )
    for n in range (10):
        print(tgS.readline())
        time.sleep(0.5)

progtest()
"""
