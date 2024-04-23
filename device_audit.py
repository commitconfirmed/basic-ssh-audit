#!/usr/bin/python
import warnings
from getpass import getpass

with warnings.catch_warnings():
	warnings.filterwarnings("ignore", category = DeprecationWarning)
	from paramiko import client
	from datetime import datetime
	from sys import exit
	import time
	import threading
	import logging

def myUserPassStruct():
	username = input("Provide Username:\n")
	password = getpass()
	return username, password

def generateTimingOffset(inTimeSecs):
	return time.time() + inTimeSecs

def _timeStamp():
	return str(datetime.utcnow())

def myLogger(logType, logMsg):
	if logType == "error": logging.error( _timeStamp() + " " + logMsg )
	elif logType == "debug": logging.debug( _timeStamp() + " " + logMsg )
	elif logType == "info": logging.info( _timeStamp() + " " + logMsg )
	else: 
		raise NotImplementedError("This program doesn't support the logging type requested.")
	return

class ssh (object):
	timeout = 10
	def __init__(self, address, username, password):
		self.interruptFlag = True
		try:
			myLogger("debug", "Connecting to " + address)
			self.client = client.SSHClient()
			self.client.set_missing_host_key_policy(client.AutoAddPolicy())
			self.client.connect(address, username=username, password=password, timeout = self.timeout, look_for_keys=False)
			transportState = repr(self.client.get_transport())
			if "active" not in transportState:
				raise RuntimeError("Transport state is not as expected. : \n"+ str(transportState))
		except Exception as e:
			self.client.close()
			self.client = None
			self.connErr = e

	def sendCommand(self, command, bufferSize=1024):
		if(self.client):
			self.data = str()
			stdin, stdout, stderr = self.client.exec_command(command, timeout = self.timeout)
			timeLimit = generateTimingOffset(30)
			while not stdout.channel.exit_status_ready() and time.time() <= timeLimit:
				if stdout.channel.recv_ready():
					self.data += stdout.channel.recv(bufferSize).decode()
			timeLimit = generateTimingOffset(60)
			while time.time() <= timeLimit:
				remainder = stdout.channel.recv(bufferSize)
				if len(remainder) == 0:
					self.interruptFlag = False
					break
				else:
					self.data += remainder.decode()
			if self.interruptFlag:
				myLogger("error", "Partial data obtained. Couldn't collect data in allowed time limit.\n" + self.data)
				if stderr.channel.recv_stderr_ready():
					myLogger("error", "\n" + stderr.read())
				raise ValueError("See log file for more details.")
			elif not stderr.channel.recv_stderr_ready() and len(self.data) == 0:
				myLogger("info", "No output from command, stderror stream from channel doesn't have data to read.")
			elif stderr.channel.recv_stderr_ready():
				myLogger("error", "\n" +  stderr.read())
			elif len(self.data):
				myLogger("debug", "Data obtained as expected on " + repr(self.client.get_transport()))
				return self.data
			else:
				raise RuntimeError("Data collection in unexpected state. Terminating.")
		else:
			myLogger("error",  "Connection not opened: \n " + str(self.connErr))
			exit(1)

	def clearConnection(self):
		if isinstance(self.client, client.SSHClient) and self.__class__.__name__ == ssh.__name__:
			myLogger("info", "Closing SSH client: " + repr(self))
			self.client.close()
		else:
			myLogger("error", "No SSH client object to close. Not expected.")
			exit(1)

def serverHandler(server, connection, command, serverThreadObjects):
	myLogger("info", "Thread for analysis on server == " + server + " started")
	output = connection.sendCommand(command)
	serverThreadObjects[server] = output
	myLogger("info", "Thread for analysis on server == " + server + " completed.\n")
	myLogger("info", "Length of output = " + str(len(str(serverThreadObjects[server]))))
	connection.clearConnection()

def main():
	logging.basicConfig(filename='device-log.txt',level=logging.INFO)
	# --- Uncomment the relevant servers/domain list for the environment you are executing against ---
	###
	# Test
	###
	#"""
	domain = ""
	servers = ["172.20.0.211", "172.20.0.212"]
	#"""
	###
	# Prod
	###
	"""
	domain = ".local"
	servers = ["ceos-r1", "ceos-r2", "ceos-r3", "ceos-r4"] 
	""" 
	# Begin building thread lists with specified command
	user, passwd = myUserPassStruct()
	command = "show version"
	threadList, sshObjList =  list(), list()
	serverThreadObjects = dict.fromkeys(servers)
	print("Starting SSH threads...")
	for c, server in enumerate(servers):
		sshObjList.append(ssh(server + domain, user, passwd))
		threadList.append(threading.Thread(target=serverHandler, args=(server, sshObjList[c], command, serverThreadObjects)))
	# Start all threads
	for thread in threadList:
		thread.start()
	# Wait for all threads to finish
	for thread in threadList:
		thread.join()
	# Write all output
	print("Finished SSH threads... \n Results: ")
	filename = "device-output.txt"
	myfile = open(filename, 'w')
	for s in servers:
		myfile.write(user + "@" + s + domain + "> " + command + "\n")
		if serverThreadObjects[s] == None:
			print("[FAIL]: " + s)
		else:
			print("[Pass]: " + s)
			myfile.write(serverThreadObjects[s])	
	myfile.close()
	
if __name__ == "__main__":
	main()
