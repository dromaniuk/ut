from bs4 import BeautifulSoup
from urllib.request import urlopen, Request
from multiprocessing import cpu_count
import urllib.parse
import http.client
import re
import sys
import os
import getopt
import time
import pprint
import datetime
import base64
import threading
import ssl
import socket
import logging
import configparser

class UT(object):
	"""docstring for UT"""

	# Main flags
	verbose = False
	quiet = False
	deep = None
	threads = cpu_count()
	service_threads = 1

	# Allowable display flags
	withinternal = False
	withcrossite = False
	withexternal = False
	withunknown = False
	withcontent = False
	withstatic = False
	withhtml = False
	withredirects = False
	with4xx = True
	with5xx = True
	withmixedcontent = True

	# Restrictable display flags
	withoutinternal = False
	withoutcrossite = False
	withoutexternal = False
	withoutunknown = False
	withoutcontent = False
	withoutstatic = False
	withouthtml = False
	withoutredirects = False
	without4xx = False
	without5xx = False
	withoutmixedcontent = False

	# Main algorithm units
	sites = set()
	urlmeta = {}
	queue = set()
	processed = set()

	# Positional units
	internal = set()
	crossite = set()
	external = set()

	# Type units
	content = set()
	static = set()
	html = set()

	# Status units
	successful = set()
	redirected = set()
	clientsideerror = set()
	serversideerror = set()
	troubled = set()

	# Support units
	crossprotocol = set()

	def read_params(self,mainargs):
		try:
			opts, args = getopt.getopt(mainargs, "hvqesd:t:", ["help","verbose","quiet",
				"with-internal",
				"with-cross",
				"with-external",
				"with-unknown",
				"with-content",
				"with-static",
				"with-html",
				"with-redirects",
				"with-4xx",
				"with-5xx",
				"with-mixed",

				"without-internal",
				"without-cross",
				"without-external",
				"without-unknown",
				"without-content",
				"without-static",
				"without-html",
				"without-redirects",
				"without-4xx",
				"without-5xx",
				"without-mixed"
			])
		except getopt.GetoptError as err:
			print(err)
			sys.exit(2)

		for o, a in opts:
			if o in ("-h", "--help"):
				print("Help text coming soon")
				sys.exit()

			elif o in ("-v", "--verbose"):
				self.verbose = True
			elif o in ("-q", "--quiet"):
				self.quiet = True
			elif o in ("-e"):
				self.extended = True
			# elif o in ("-s"):
			# 	self.showsummary = True
			elif o in ("-d"):
				self.deep = int(a)
			elif o in ("-t"):
				self.threads = int(a)

			elif o in ("--with-internal"):
				self.withinternal = True
			elif o in ("--with-cross"):
				self.withcrossite = True
			elif o in ("--with-external"):
				self.withexternal = True
			elif o in ("--with-unknown"):
				self.withunknown = True
			elif o in ("--with-content"):
				self.withcontent = True
			elif o in ("--with-static"):
				self.withstatic = True
			elif o in ("--with-html"):
				self.withhtml = True
			elif o in ("--with-4xx"):
				self.with4xx = True
			elif o in ("--with-5xx"):
				self.with5xx = True
			elif o in ("--with-mixed"):
				self.withmixedcontent = True

			elif o in ("--without-internal"):
				self.withoutinternal = True
			elif o in ("--without-cross"):
				self.withoutcrossite = True
			elif o in ("--without-external"):
				self.withoutexternal = True
			elif o in ("--without-unknown"):
				self.withoutunknown = True
			elif o in ("--without-content"):
				self.withoutcontent = True
			elif o in ("--without-static"):
				self.withoutstatic = True
			elif o in ("--without-html"):
				self.withouthtml = True
			elif o in ("--without-redirects"):
				self.withoutredirects = True
			elif o in ("--without-4xx"):
				self.without4xx = True
			elif o in ("--without-5xx"):
				self.without5xx = True
			elif o in ("--with-mixed"):
				self.withoutmixedcontent = True

			else:
				assert False, "unhandled option"

		if len(args) > 0:
			for u in args:
				D = urllib.parse.urlparse(u)
				if D.scheme == '':
					domain = D.path
					nonwww = re.search('^(www\.)?(.*)$',domain).group(2)
					path = "/"

					D = D._replace(scheme='http',netloc=nonwww,path=path)
					self.sites.add(urllib.parse.urlunparse(D))

				elif set([D.scheme]).issubset(set(['http','https'])):
					domain = D.netloc
					nonwww = re.search('^(www\.)?(.*)$',domain).group(2)

					D = D._replace(netloc=nonwww)
					self.sites.add(urllib.parse.urlunparse(D))

				else:
					logging.warning("Unsupported protocol %s",D.scheme)
					continue

		else:
			assert False, "wrong input parameters"

	def __init__(self):
		try:
			self.configure()
			self.read_params(sys.argv[1:])

			self.scan()
		except (SystemExit, BrokenPipeError):
			pass
		except Exception as e:
			logging.critical(str(e))
			raise e

	def configure(self):
		self.workdir = str(os.path.expanduser("~")) + "/.ut/"
		try:
			os.stat(self.workdir)
		except:
			os.mkdir(self.workdir)

		self.configfile = self.workdir + "main.conf"
		self.config = configparser.ConfigParser()
		self.config.read( self.configfile )
		ms = "DEFAULT"

		loglevel = self.config.get(ms,"loglevel")
		if loglevel == 'debug':
			self.loglevel = logging.DEBUG
		elif loglevel == 'info':
			self.loglevel = logging.INFO
		elif loglevel == 'warn':
			self.loglevel = logging.WARNING
		elif loglevel == 'error':
			self.loglevel = logging.ERROR
		elif loglevel == 'crit':
			self.loglevel = logging.CRITICAL
		else:
			raise ConfigException('Loglevel "' + loglevel + '" not recognized')

		self.logfile = self.workdir + time.strftime("%Y%m%d%H%M%S") + ".log"
		logging.basicConfig(filename=self.logfile,level=self.loglevel,format="%(asctime)s [%(levelname)s]\t%(message)s")
		logging.debug("Logfile opened")

		logging.debug("Creating lock")
		self.lock = threading.Lock()


	def display(self):
		while self.mon_thread_enabled:
			sys.stdout.write("\rTrds: {0:2d}\tQueue: {1:2d}\tSucc: {2:2d}\tSkip: {3:2d}\tExt: {4:3d}\tRedir: {5:2d}\tErr: {6:3d}\tTrb: {7:2d}".format(threading.active_count()-self.service_threads,len(self.queue),len(self.successful),len(self.skipped),len(self.external),len(self.redirected),len(self.errored),len(self.troubled)))
			sys.stdout.flush()
			time.sleep(.5)

	def suredir(self,directory):
		try:
			os.stat(directory)
		except:
			os.mkdir(directory)

	def push(self,url,ref,deep):
		self.lock.acquire()
		self.processed.add(url)
		self.queue.add(url)
		self.urlmeta[url] = {
			"referers" : set([ref,]),
			"deep" : deep
		}
		self.lock.release()

	def pop(self):
		self.lock.acquire()
		url = self.queue.pop()
		self.lock.release()
		return url

	def scan(self):
		for site in self.sites:
			self.push(site,'',0)
			self.internal.add(site)

		logging.debug("Printing startup info")
		print("\033[0;36mSites:\033[0m " + " ".join(self.sites))
		print("\033[0;36mThreads:\033[0m " + str(self.threads))
		deep = "Infinite"
		if self.deep is not None:
			deep = self.deep
		print("\033[0;36mDeep:\033[0m {}".format(deep))
		print("\033[0;36mLogfile:\033[0m " + os.path.abspath(self.logfile))
		print()
		logging.info("Threads count: %d",self.threads)

		try:
			logging.debug("Configuring service threads")
			self.mon_thread_enabled = True
			main_thread = threading.main_thread()
			if self.quiet:
				logging.debug("Quiet mode enabled. Running thread for displaying stats")
				mon_thread = threading.Thread(target=self.display)
				mon_thread.start()
			self.service_threads = threading.active_count()
			logging.debug("Service threads: %d",self.service_threads)
			logging.debug("Processing")
			while True:
				while threading.active_count()-self.service_threads < self.threads and len(self.queue) > 0:
					logging.debug("Runned %d thread(s). Queue %d",threading.active_count(),len(self.queue))
					url = self.pop()
					ref = self.urlmeta[url]['referers'].pop()
					deep = self.urlmeta[url]['deep']
					# if not isinstance(urllib.parse.urlparse(url),urllib.parse.ParseResult):
					# 	logging.debug("%s is not valid url. Skipping")
					# 	continue

					if self.deep is None or self.deep >= deep:
						t = threading.Thread(name="Parsing " + url,target=self.chain, args=(url,ref,deep))
						t.start()

				if len(self.queue) == 0:
					logging.debug("Queue empty. Syncronizing threads")
					for t in threading.enumerate():
						if t is main_thread:
							continue
						if self.quiet:
							if t is mon_thread:
								continue
						t.join()
					if len(self.queue) == 0:
						logging.debug("Threads syncronized. Queue still empty. Exiting")
						break
				else:
					time.sleep(.1)
		except BrokenPipeError:
			pass
		except KeyboardInterrupt:
			logging.warning("Operation aborted. Exiting")
			sys.stdout.write("\r" + " "*120 + "\r\033[1;36mOperation Aborted\033[0m\n")
			sys.stdout.flush()
		except:
			raise
		finally:
			logging.debug("Syncronizing threads")
			self.mon_thread_enabled = False
			main_thread = threading.main_thread()
			for t in threading.enumerate():
				if t is main_thread:
					continue
				t.join()
			logging.debug("Threads syncronized")

			logging.debug("Displaying summary")
			sys.stdout.write("\r" + " "*120 + "\r\n" )
			sys.stdout.flush()

			if len(self.html & self.internal):
				logging.info("Pages Internal: %d",len(self.html & self.internal))
				print("\033[1;30mPages Internal:\033[0m \033[1;37m{0:0d}\033[0m".format(len(self.html & self.internal)))
			if len(self.html & self.internal & self.successful):
				logging.info("    Successful: %d",len(self.html & self.internal & self.successful))
				print("\033[1;30m    Successful:\033[0m\t\t\033[0;32m{0:4d}\033[0m".format(len(self.html & self.internal & self.successful)))
			if len(self.html & self.internal & self.redirected):
				logging.info("    Redirected: %d",len(self.html & self.internal & self.redirected))
				print("\033[1;30m    Redirected:\033[0m\t\t\033[0;34m{0:4d}\033[0m".format(len(self.html & self.internal & self.redirected)))
			if len(self.html & self.internal & self.clientsideerror):
				logging.info("    4xx Errors: %d",len(self.html & self.internal & self.clientsideerror))
				print("\033[1;30m    4xx Errors:\033[0m\t\t\033[0;33m{0:4d}\033[0m".format(len(self.html & self.internal & self.clientsideerror)))
			if len(self.html & self.internal & self.serversideerror):
				logging.info("    5xx Errors: %d",len(self.html & self.internal & self.serversideerror))
				print("\033[1;30m    5xx Errors:\033[0m\t\t\033[0;31m{0:4d}\033[0m".format(len(self.html & self.internal & self.serversideerror)))
			if len(self.html & self.internal & self.crossprotocol):
				logging.info("    Crossprotocol: %d",len(self.html & self.internal & self.crossprotocol))
				print("\033[1;30m    Crossprotocol:\033[0m\t\033[0;33m{0:4d}\033[0m".format(len(self.html & self.internal & self.crossprotocol)))

			if len(self.html & self.crossite):
				logging.info("Pages Crosssite: %d",len(self.html & self.crossite))
				print("\033[1;30mPages Crosssite:\033[0m \033[1;37m{0:0d}\033[0m".format(len(self.html & self.crossite)))
			if len(self.html & self.crossite & self.successful):
				logging.info("    Successful: %d",len(self.html & self.crossite & self.successful))
				print("\033[1;30m    Successful:\033[0m\t\t\033[0;32m{0:4d}\033[0m".format(len(self.html & self.crossite & self.successful)))
			if len(self.html & self.crossite & self.redirected):
				logging.info("    Redirected: %d",len(self.html & self.crossite & self.redirected))
				print("\033[1;30m    Redirected:\033[0m\t\t\033[0;34m{0:4d}\033[0m".format(len(self.html & self.crossite & self.redirected)))
			if len(self.html & self.crossite & self.clientsideerror):
				logging.info("    4xx Errors: %d",len(self.html & self.crossite & self.clientsideerror))
				print("\033[1;30m    4xx Errors:\033[0m\t\t\033[0;33m{0:4d}\033[0m".format(len(self.html & self.crossite & self.clientsideerror)))
			if len(self.html & self.crossite & self.serversideerror):
				logging.info("    5xx Errors: %d",len(self.html & self.crossite & self.serversideerror))
				print("\033[1;30m    5xx Errors:\033[0m\t\t\033[0;31m{0:4d}\033[0m".format(len(self.html & self.crossite & self.serversideerror)))
			if len(self.html & self.crossite & self.crossprotocol):
				logging.info("    Crossprotocol: %d",len(self.html & self.crossite & self.crossprotocol))
				print("\033[1;30m    Crossprotocol:\033[0m\t\033[0;33m{0:4d}\033[0m".format(len(self.html & self.crossite & self.crossprotocol)))

			if len(self.content & self.internal):
				logging.info("Content Internal: %d",len(self.content & self.internal))
				print("\033[1;30mContent Internal:\033[0m \033[1;37m{0:0d}\033[0m".format(len(self.content & self.internal)))
			if len(self.content & self.internal & self.successful):
				logging.info("    Successful: %d",len(self.content & self.internal & self.successful))
				print("\033[1;30m    Successful:\033[0m\t\t\033[0;32m{0:4d}\033[0m".format(len(self.content & self.internal & self.successful)))
			if len(self.content & self.internal & self.redirected):
				logging.info("    Redirected: %d",len(self.content & self.internal & self.redirected))
				print("\033[1;30m    Redirected:\033[0m\t\t\033[0;34m{0:4d}\033[0m".format(len(self.content & self.internal & self.redirected)))
			if len(self.content & self.internal & self.clientsideerror):
				logging.info("    4xx Errors: %d",len(self.content & self.internal & self.clientsideerror))
				print("\033[1;30m    4xx Errors:\033[0m\t\t\033[0;33m{0:4d}\033[0m".format(len(self.content & self.internal & self.clientsideerror)))
			if len(self.content & self.internal & self.serversideerror):
				logging.info("    5xx Errors: %d",len(self.content & self.internal & self.serversideerror))
				print("\033[1;30m    5xx Errors:\033[0m\t\t\033[0;31m{0:4d}\033[0m".format(len(self.content & self.internal & self.serversideerror)))
			if len(self.content & self.internal & self.crossprotocol):
				logging.info("    Crossprotocol: %d",len(self.content & self.internal & self.crossprotocol))
				print("\033[1;30m    Crossprotocol:\033[0m\t\033[0;33m{0:4d}\033[0m".format(len(self.content & self.internal & self.crossprotocol)))

			if len(self.content & self.crossite):
				logging.info("Content Crosssite: %d",len(self.content & self.crossite))
				print("\033[1;30mContent Crosssite:\033[0m \033[1;37m{0:0d}\033[0m".format(len(self.content & self.crossite)))
			if len(self.content & self.crossite & self.successful):
				logging.info("    Successful: %d",len(self.content & self.crossite & self.successful))
				print("\033[1;30m    Successful:\033[0m\t\t\033[0;32m{0:4d}\033[0m".format(len(self.content & self.crossite & self.successful)))
			if len(self.content & self.crossite & self.redirected):
				logging.info("    Redirected: %d",len(self.content & self.crossite & self.redirected))
				print("\033[1;30m    Redirected:\033[0m\t\t\033[0;34m{0:4d}\033[0m".format(len(self.content & self.crossite & self.redirected)))
			if len(self.content & self.crossite & self.clientsideerror):
				logging.info("    4xx Errors: %d",len(self.content & self.crossite & self.clientsideerror))
				print("\033[1;30m    4xx Errors:\033[0m\t\t\033[0;33m{0:4d}\033[0m".format(len(self.content & self.crossite & self.clientsideerror)))
			if len(self.content & self.crossite & self.serversideerror):
				logging.info("    5xx Errors: %d",len(self.content & self.crossite & self.serversideerror))
				print("\033[1;30m    5xx Errors:\033[0m\t\t\033[0;31m{0:4d}\033[0m".format(len(self.content & self.crossite & self.serversideerror)))
			if len(self.content & self.crossite & self.crossite):
				logging.info("    Crossprotocol: %d",len(self.content & self.crossite & self.crossprotocol))
				print("\033[1;30m    Crossprotocol:\033[0m\t\033[0;33m{0:4d}\033[0m".format(len(self.content & self.crossite & self.crossprotocol)))

			if len(self.content & self.external):
				logging.info("  External: %d",len(self.content & self.external))
				print("\033[1;30mContent External:\033[0m \033[1;37m{0:0d}\033[0m".format(len(self.content & self.external)))
			if len(self.content & self.external & self.successful):
				logging.info("    Successful: %d",len(self.content & self.external & self.successful))
				print("\033[1;30m    Successful:\033[0m\t\t\033[0;32m{0:4d}\033[0m".format(len(self.content & self.external & self.successful)))
			if len(self.content & self.external & self.redirected):
				logging.info("    Redirected: %d",len(self.content & self.external & self.redirected))
				print("\033[1;30m    Redirected:\033[0m\t\t\033[0;34m{0:4d}\033[0m".format(len(self.content & self.external & self.redirected)))
			if len(self.content & self.external & self.clientsideerror):
				logging.info("    4xx Errors: %d",len(self.content & self.external & self.clientsideerror))
				print("\033[1;30m    4xx Errors:\033[0m\t\t\033[0;33m{0:4d}\033[0m".format(len(self.content & self.external & self.clientsideerror)))
			if len(self.content & self.external & self.serversideerror):
				logging.info("    5xx Errors: %d",len(self.content & self.external & self.serversideerror))
				print("\033[1;30m    5xx Errors:\033[0m\t\t\033[0;31m{0:4d}\033[0m".format(len(self.content & self.external & self.serversideerror)))
			if len(self.content & self.external & self.crossprotocol):
				logging.info("    Crossprotocol: %d",len(self.content & self.external & self.crossprotocol))
				print("\033[1;30m    Crossprotocol:\033[0m\t\033[0;33m{0:4d}\033[0m".format(len(self.content & self.external & self.crossprotocol)))

			if len(self.static - self.content & self.internal):
				logging.info("Static Internal: %d",len(self.static - self.content & self.internal))
				print("\033[1;30mStatic Internal:\033[0m \033[1;37m{0:0d}\033[0m".format(len(self.static - self.content & self.internal)))
			if len(self.static - self.content & self.internal & self.successful):
				logging.info("    Successful: %d",len(self.static - self.content & self.internal & self.successful))
				print("\033[1;30m    Successful:\033[0m\t\t\033[0;32m{0:4d}\033[0m".format(len(self.static - self.content & self.internal & self.successful)))
			if len(self.static - self.content & self.internal & self.redirected):
				logging.info("    Redirected: %d",len(self.static - self.content & self.internal & self.redirected))
				print("\033[1;30m    Redirected:\033[0m\t\t\033[0;34m{0:4d}\033[0m".format(len(self.static - self.content & self.internal & self.redirected)))
			if len(self.static - self.content & self.internal & self.clientsideerror):
				logging.info("    4xx Errors: %d",len(self.static - self.content & self.internal & self.clientsideerror))
				print("\033[1;30m    4xx Errors:\033[0m\t\t\033[0;33m{0:4d}\033[0m".format(len(self.static - self.content & self.internal & self.clientsideerror)))
			if len(self.static - self.content & self.internal & self.serversideerror):
				logging.info("    5xx Errors: %d",len(self.static - self.content & self.internal & self.serversideerror))
				print("\033[1;30m    5xx Errors:\033[0m\t\t\033[0;31m{0:4d}\033[0m".format(len(self.static - self.content & self.internal & self.serversideerror)))
			if len(self.static - self.content & self.internal & self.crossite):
				logging.info("    Crossprotocol: %d",len(self.static - self.content & self.internal & self.crossprotocol))
				print("\033[1;30m    Crossprotocol:\033[0m\t\033[0;33m{0:4d}\033[0m".format(len(self.static - self.content & self.internal & self.crossprotocol)))

			if len(self.static - self.content & self.crossite):
				logging.info("  Crosssite: %d",len(self.static - self.content & self.crossite))
				print("\033[1;30mStatic Crosssite:\033[0m \033[1;37m{0:0d}\033[0m".format(len(self.static - self.content & self.crossite)))
			if len(self.static - self.content & self.crossite & self.successful):
				logging.info("    Successful: %d",len(self.static - self.content & self.crossite & self.successful))
				print("\033[1;30m    Successful:\033[0m\t\t\033[0;32m{0:4d}\033[0m".format(len(self.static - self.content & self.crossite & self.successful)))
			if len(self.static - self.content & self.crossite & self.redirected):
				logging.info("    Redirected: %d",len(self.static - self.content & self.crossite & self.redirected))
				print("\033[1;30m    Redirected:\033[0m\t\t\033[0;34m{0:4d}\033[0m".format(len(self.static - self.content & self.crossite & self.redirected)))
			if len(self.static - self.content & self.crossite & self.clientsideerror):
				logging.info("    4xx Errors: %d",len(self.static - self.content & self.crossite & self.clientsideerror))
				print("\033[1;30m    4xx Errors:\033[0m\t\t\033[0;33m{0:4d}\033[0m".format(len(self.static - self.content & self.crossite & self.clientsideerror)))
			if len(self.static - self.content & self.crossite & self.serversideerror):
				logging.info("    5xx Errors: %d",len(self.static - self.content & self.crossite & self.serversideerror))
				print("\033[1;30m    5xx Errors:\033[0m\t\t\033[0;31m{0:4d}\033[0m".format(len(self.static - self.content & self.crossite & self.serversideerror)))
			if len(self.static - self.content & self.crossite & self.crossite):
				logging.info("    Crossprotocol: %d",len(self.static - self.content & self.crossite & self.crossprotocol))
				print("\033[1;30m    Crossprotocol:\033[0m\t\033[0;33m{0:4d}\033[0m".format(len(self.static - self.content & self.crossite & self.crossprotocol)))



				# print("Success: " + str(len(self.successful)))
				# print("\tInternal: " + str(len(self.successful & self.internal)))
				# print("\tCrossdomain: " + str(len(self.successful & self.crossite)))
				# print("\tExternal: " + str(len(self.successful & self.external)))
				# print("\tUnknown: " + str(len(self.successful - (self.internal | self.crossite | self.external))))

			# if len(self.crossprotocol):
			# 	logging.info("Mixed content: %d",len(self.crossprotocol & self.content))
			# 	logging.info("\nInternal: %d",len(self.internal & self.content & self.crossprotocol))
			# 	print("Mixed content: " + str(len(self.crossprotocol & self.content)))
			# 	print("\tSuccess: " + str(len(self.internal & self.content & self.crossprotocol)))

			# if len(self.redirected):
			# 	logging.info("Redirected: %d",len(self.redirected))
			# 	print("Redirected: " + str(len(self.redirected)))

			# if len(self.clientsideerror):
			# 	logging.info("Not Found: %d",len(self.clientsideerror))
			# 	print("4xx Errors: " + str(len(self.clientsideerror)))

			# if len(self.serversideerror):
			# 	logging.info("5xx Errors: %d",len(self.serversideerror))
			# 	print("5xx Errors: " + str(len(self.serversideerror)))

			# if len(self.troubled):
			# 	logging.info("Troubled: %d",len(self.troubled))
			# 	print("Troubled: " + str(len(self.troubled)))
			print("\n")

	def chain(self,url,ref,deep):
		try:
			logging.debug("[%s] Chain started. Referer %s. Deep %d",url,ref,deep)
			self.urlmeta[url]['referers'].add(ref)

			URL = urllib.parse.urlparse(url)
			if URL.scheme == 'http':
				logging.debug("[%s] Scheme %s",url,URL.scheme)
				conn = http.client.HTTPConnection(URL.netloc)
			elif URL.scheme == 'https':
				logging.debug("[%s] Scheme %s",url,URL.scheme)
				conn = http.client.HTTPSConnection(URL.netloc)
			else:
				logging.debug("[%s] Scheme %s. Skipping",url,URL.scheme)
				return

			logging.debug("[%s] Requesting %s for the page %s",url,URL.netloc,URL.path)
			try:
				bpath = URL.path.encode()
				path = bpath.decode('ascii')
			except:
				path = urllib.parse.quote(URL.path)

			conn.request("GET", path, None, {'User-Agent':'Hadornbot'})
			resp = conn.getresponse()

			logging.debug("[%s] %d %s",url,resp.status,resp.reason)
			self.urlmeta[url]['status'] = resp.status
			self.urlmeta[url]['reason'] = resp.reason

			if resp.status//100 == 2:
				self.code_2xx(url,URL,resp,ref,deep)
			elif resp.status//100 == 3:
				self.code_3xx(url,URL,resp,ref,deep)
			elif resp.status//100 == 4:
				self.code_4xx(url,URL,resp,ref,deep)
			elif resp.status//100 == 5:
				self.code_5xx(url,URL,resp,ref,deep)
			else:
				print(str(resp.status) + "\t" + resp.reason)
				return
		except (KeyboardInterrupt,BrokenPipeError):
			pass
		except (http.client.BadStatusLine, ssl.SSLError, ssl.CertificateError, ConnectionRefusedError, socket.gaierror) as err:
			trouble = str(err)
			self.troubled.add(url)
			self.urlmeta[url]['trouble'] = trouble
			logging.error("[%s] %s",url,trouble)
			if not self.quiet:
				print("\t".join([str(err),url,"(Ref:" + ref + ")"]))
		except UnicodeEncodeError as e:
			print("UnicodeEncodeError: " +URL.netloc + " " + URL.path)
			# raise e
		except:
			raise
		finally:
			if set([url]).issubset(self.successful):
				status = self.urlmeta[url]['status']
				reason = self.urlmeta[url]['reason']

				descr = []
				tags = []
				disp = False

				if set([url]).issubset(self.internal):
					disp |= self.withinternal or self.verbose
					descr.append('Internal')
					# tags.append('Intr')
				elif set([url]).issubset(self.crossite):
					disp |= self.withcrossite or self.verbose
					descr.append('Crosssite')
					tags.append('Cross')
				elif set([url]).issubset(self.external):
					disp |= self.withexternal or self.verbose
					descr.append('External')
					tags.append('Extr')
				else:
					disp |= self.withunknown or self.verbose
					descr.append('Unknown')
					tags.append('Unknown')

				if set([url]).issubset(self.content):
					disp |= self.withcontent or self.verbose
					descr.append('Content')
					tags.append('Cont')
				elif set([url]).issubset(self.static-self.content):
					disp |= self.withstatic or self.verbose
					descr.append('Link')
					tags.append('Link')
				else:
					disp |= self.withhtml or self.verbose
					descr.append('HTML')
					# tags.append('HTML')

				if set([url]).issubset(self.crossprotocol & self.content):
					disp |= self.withmixedcontent or self.verbose
					descr.append('Mixed')
					tags.append('\033[1;31mMixed\033[0m')

				disp &= not self.withoutinternal
				disp &= not self.withoutcrossite
				disp &= not self.withoutexternal
				disp &= not self.withoutunknown
				disp &= not self.withoutcontent
				disp &= not self.withoutstatic
				disp &= not self.withouthtml
				disp &= not self.withoutmixedcontent

				logging.info("%d\t%s\t|%s|\t%s\t(Ref: %s)",status,reason," ".join(descr),url,ref)
				if not self.quiet and disp:
					# print("\t".join([str(status),reason,"|" + "/".join(tags) + "|",url,"(Ref: "+ref+")"]))
					print("\033[0;32m{status:3d} {reason:20}\033[0m {tags:15}\t\033[0;37m{url}\033[0m \033[1;30m(Ref: {ref})\033[0m".format(status=status,reason=reason,tags="/".join(tags),url=url,ref=ref))

			if set([url]).issubset(self.redirected):
				status = self.urlmeta[url]['status']
				reason = self.urlmeta[url]['reason']

				disp = False
				descr = []
				tags = []
				if set([url]).issubset(self.crossprotocol & self.content):
					disp |= (self.withmixedcontent or self.verbose) and not self.withoutmixedcontent
					descr.append('Mixed')
					tags.append('\033[1;31mMixed\033[0m')
				if set([url]).issubset(self.content):
					disp |= (self.withcontent or self.verbose) and not self.withoutcontent
					descr.append('Content')
					tags.append('Cont')

				logging.info("%d\t%s\t%s\t%s => %s\t(Ref: %s)",status,reason,"/".join(descr),url,self.urlmeta[url]['location'],ref)
				# print(self.quiet, (self.withredirects or self.verbose or disp), self.withoutredirects)
				if not self.quiet and (self.withredirects or self.verbose or disp) and not self.withoutredirects:
					print("\033[1;34m{status:3d} {reason:20}\033[0m {tags:15}\t\033[0;37m{url} => {location}\033[0m \033[1;30m(Ref: {ref})\033[0m".format(status=status,reason=reason,tags="/".join(tags),url=url,location=self.urlmeta[url]['location'],ref=ref))

			if set([url]).issubset(self.clientsideerror):
				status = self.urlmeta[url]['status']
				reason = self.urlmeta[url]['reason']

				logging.warning("%d\t%s\t%s\t(Ref: %s)",status,reason,url,ref)
				if not self.quiet:
					if (self.with4xx or self.verbose) and not self.without4xx:
						print("\033[0;33m{status:3d} {reason:20}\033[0m {tags:15}\t\033[0;37m{url}\033[0m \033[1;30m(Ref: {ref})\033[0m".format(status=status,reason=reason,tags='',url=url,ref=ref))

			if set([url]).issubset(self.serversideerror):
				status = self.urlmeta[url]['status']
				reason = self.urlmeta[url]['reason']

				logging.warning("%d\t%s\t%s\t(Ref: %s)",status,reason,url,ref)
				if not self.quiet:
					print("\t".join([str(status),reason,url,"(Ref: "+ref+")"]))

	def code_2xx(self,url,URL,resp,ref,deep):
		mime = resp.getheader("Content-Type")
		logging.debug("[%s] Content type: %s",url,mime)

		self.successful.add(url)
		self.urlmeta[url]['mime'] = mime

		if re.search('^text/html', mime):
			self.html.add(url)
			self.mime_html(url,URL,resp,ref,deep)
		else:
			logging.info("[%s] OK. Skipping",url)
			self.static.add(url)

	def mime_html(self,url,URL,resp,ref,deep):
		if set([url]).issubset( self.internal | self.crossite ):
			html_page = resp.read()
			logging.debug("[%s] Parsing page",url)
			soup = BeautifulSoup(html_page,'html.parser')

			self.tags_a(url,URL,ref,deep,soup)
			self.tags_script(url,URL,ref,deep,soup)
			self.tags_css(url,URL,ref,deep,soup)
			self.tags_imgs(url,URL,ref,deep,soup)

	def tags_a(self,url,URL,ref,deep,soup):
		logging.debug("[%s] Searching links",url)
		for tag in soup.findAll("a"):
			pointer = tag.get('href')
			if pointer:
				pointer, P = self.prepare_url(pointer,url)
				logging.debug("[%s] Found link %s",url,pointer)
				self.url(url,URL,ref,deep,P,pointer)

	def tags_script(self,url,URL,ref,deep,soup):
		logging.debug("[%s] Searching scripts",url)
		for tag in soup.findAll("script"):
			pointer = tag.get('src')
			if pointer:
				pointer, P = self.prepare_url(pointer,url)
				logging.debug("[%s] Found script %s",url,pointer)
				self.content.add(pointer)
				self.url(url,URL,ref,deep,P,pointer)

	def tags_css(self,url,URL,ref,deep,soup):
		logging.debug("[%s] Searching stylesheets",url)
		for tag in soup.findAll("link"):
			rel = tag.get('rel')
			if rel is not None and 'stylesheet' in rel:
				pointer = tag.get('href')
				if pointer:
					pointer, P = self.prepare_url(pointer,url)
					logging.debug("[%s] Found stylesheet %s",url,pointer)
					self.content.add(pointer)
					self.url(url,URL,ref,deep,P,pointer)

	def tags_imgs(self,url,URL,ref,deep,soup):
		logging.debug("[%s] Searching images",url)
		for tag in soup.findAll("img"):
			pointer = tag.get('src')
			if pointer:
				pointer, P = self.prepare_url(pointer,url)
				logging.debug("[%s] Found stylesheet %s",url,pointer)
				self.content.add(pointer)
				self.url(url,URL,ref,deep,P,pointer)

	def prepare_url(self,pointer,url):
		pointer = urllib.parse.urljoin(url, pointer)
		P = urllib.parse.urlparse(pointer)
		P = P._replace(params='',fragment='',netloc=P.netloc.replace(":443",""))
		return urllib.parse.urlunparse(P), P

	def url(self,url,URL,ref,deep,P,pointer):
		if not set([pointer]).issubset(self.processed):
			self.processed.add(pointer)
			if P.scheme in ('http','https'):
				if P.scheme != URL.scheme:
					logging.debug("[%s] Crossprotocol link",url)
					self.crossprotocol.add(pointer)

				external, internal = self.get_position(P,URL)
				if internal:
					logging.debug("[%s] Internal link. Adding to queue",url)
					self.internal.add(pointer)
					self.push(pointer,url,deep+1)
				elif external:
					logging.debug("[%s] External link",url)
					self.external.add(pointer)
					if set([pointer]).issubset(self.content):
						self.push(pointer,url,deep+1)
				else:
					logging.debug("[%s] Internal crossite link. Adding to queue",url)
					self.crossite.add(pointer)
					self.push(pointer,url,deep+1)

	def get_position(self,P,URL):
		urlsite = ''
		pointersite = ''
		for s in self.sites:
			S = urllib.parse.urlparse(s)
			if (URL.netloc.find(S.netloc) == 0 or URL.netloc.find("www." + S.netloc) == 0) and (URL.path.find(S.path) == 0) and len(s)>len(urlsite):
				urlsite = s
			if (P.netloc.find(S.netloc) == 0 or P.netloc.find("www." + S.netloc) == 0) and (P.path.find(S.path) == 0) and len(s)>len(pointersite):
				pointersite = s
		# print("'" + pointersite + "'\n'" + urlsite + "'\n\n")
		return pointersite == '', pointersite == urlsite

	def code_3xx(self,url,URL,resp,ref,deep):
		location = resp.getheader("Location");
		self.redirected.add(url)
		self.urlmeta[url]['location'] = location

		P = urllib.parse.urlparse(location)._replace(params='',fragment='')
		self.url(url,URL,ref,deep,P,location)

	def code_4xx(self,url,URL,resp,ref,deep):
		self.clientsideerror.add(url)

	def code_5xx(self,url,URL,resp,ref,deep):
		self.serversideerror.add(url)

class ConfigException(Exception):
	pass

