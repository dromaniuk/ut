#!/usr/bin/python3

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

	verbose = False
	quiet = False
	extended = False
	domain = ""
	domains = []
	starturl = None
	only_static = False
	external_static = False
	list_view = False
	showsummary = False
	deep = None
	threads = cpu_count()+1
	service_threads = 1
	withcrossprotocol = False
	withcontent = False
	withexternal = False
	withmixedcontent = False

	def read_params(self,mainargs):
		try:
			opts, args = getopt.getopt(mainargs, "hvqsed:t:", ["help","verbose","quiet","only-static","external-static","list","with-external","mixed","content","crossprotocol"])
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
			elif o in ("-s"):
				self.showsummary = True
			elif o in ("-t"):
				self.threads = int(a)
			elif o in ("-d"):
				self.deep = int(a)
			elif o in ("--only-static"):
				self.only_static = True
			elif o in ("--external-static"):
				self.external_static = True
			elif o in ("--with-external"):
				self.withexternal = True
			elif o in ("--with-mixed"):
				self.withmixedcontent = True
			elif o in ("--list"):
				self.list_view = True

			else:
				assert False, "unhandled option"

		if len(args) > 0:
			self.domain = args[0]
			for u in args:
				d = urllib.parse.urlparse(u)
				if re.search('^http(s)?://', u):
					self.domains.append(d.netloc)
				else:
					self.domains.append(d.path)
			self.domain = self.domains[0]
		else:
			assert False, "wrong input parameters"

	def __init__(self, mainargs):
		try:
			self.configure()
			self.read_params(mainargs)

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
		self.domaindir = self.workdir + self.domain + "/"
		self.suredir(self.domaindir)
		self.logfile = self.workdir + time.strftime("%Y%m%d%H%M%S") + ".log"
		logging.basicConfig(filename=self.logfile,level=self.loglevel,format="%(asctime)s [%(levelname)s]\t%(message)s")
		logging.debug("Logfile opened")

		logging.debug("Creating sets")
		self.urlmeta = {}
		self.queue = set()
		self.processed = set()

		self.successful = set()
		self.redirected = set()
		self.notfound = set()
		self.errored = set()

		self.troubled = set()
		self.skipped = set()

		self.internal = set()
		self.external = set()

		self.crossdomain = set()
		self.crossprotocol = set()
		self.sitecontent = set()

		logging.debug("Creating lock")
		self.lock = threading.Lock()

		logging.debug("Adding domains")
		for d in self.domains:
			logging.info("Domain %s", d)
			self.push("http://" + d + "/",'',0)
			self.push("https://" + d + "/",'',0)
			self.internal.add("http://" + d + "/")
			self.internal.add("https://" + d + "/")

		logging.debug("Printing startup info")
		print("Logfile: " + os.path.abspath(self.logfile))
		print("Domain: " + " ".join(self.domains))
		print("Threads: " + str(self.threads) + "\n")
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
					if not isinstance(urllib.parse.urlparse(url),urllib.parse.ParseResult):
						logging.debug("%s is not valid url. Skipping")
						continue

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
			sys.stdout.write("\r" + " "*120 + "\rOperation Aborted\n")
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
			sys.stdout.write("\r" + " "*120 + "\r" )
			sys.stdout.flush()
			# if len(self.successful):
			# 	self.log(["Success:",str(len(self.successful))])
			# if len(self.redirected):
			# 	self.log(["Redirected:",str(len(self.redirected))])
			# if len(self.errored):
			# 	self.log(["Errored:",str(len(self.errored))])
			# if len(self.troubled):
			# 	self.log(["Troubled:",str(len(self.troubled))])
			# if len(self.skipped):
			# 	self.log(["Skipped:",str(len(self.skipped))])
			# if len(self.external):
			# 	self.log(["External:",str(len(self.external))])

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
			conn.request("GET", urllib.parse.quote(URL.path))
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
				if set([url]).issubset(self.internal):
					if set([url]).issubset(self.sitecontent | self.skipped):
						logging.info("%d\t%s\tInternal HTML\t%s\t(Ref: %s)",resp.status,resp.reason,url,ref)
						if not self.quiet:
							if self.verbose or self.withcontent:
								print("\t".join([str(self.urlmeta[url]['status']),self.urlmeta[url]['reason'],"*In/cont*",url,"(Ref: "+ref+")"]))
					else:
						logging.info("%d\t%s\tInternal Content\t%s\t(Ref: %s)",resp.status,resp.reason,url,ref)
						if not self.quiet:
							if self.verbose:
								print("\t".join([str(self.urlmeta[url]['status']),self.urlmeta[url]['reason'],"*In/HTML*",url,"(Ref: "+ref+")"]))
				elif set([url]).issubset(self.crossdomain):
					if set([url]).issubset(self.sitecontent | self.skipped):
						logging.info("%d\t%s\tCrossdomain HTML\t%s\t(Ref: %s)",resp.status,resp.reason,url,ref)
						if not self.quiet:
							if self.verbose or self.withcontent:
								print("\t".join([str(self.urlmeta[url]['status']),self.urlmeta[url]['reason'],"*Cr/cont*",url,"(Ref: "+ref+")"]))
					else:
						logging.info("%d\t%s\tCrossdomain Content\t%s\t(Ref: %s)",resp.status,resp.reason,url,ref)
						if not self.quiet:
							if self.verbose:
								print("\t".join([str(self.urlmeta[url]['status']),self.urlmeta[url]['reason'],"*Cr/HTML*",url,"(Ref: "+ref+")"]))
				elif set([url]).issubset(self.external):
					if set([url]).issubset(self.sitecontent | self.skipped):
						logging.info("%d\t%s\tExternal HTML\t%s\t(Ref: %s)",resp.status,resp.reason,url,ref)
						if not self.quiet:
							if self.verbose or self.withcontent:
								print("\t".join([str(self.urlmeta[url]['status']),self.urlmeta[url]['reason'],"*Ex/cont*",url,"(Ref: "+ref+")"]))
					else:
						logging.info("%d\t%s\tExternal Content\t%s\t(Ref: %s)",resp.status,resp.reason,url,ref)
						if not self.quiet:
							if self.verbose:
								print("\t".join([str(self.urlmeta[url]['status']),self.urlmeta[url]['reason'],"*Ex/HTML*",url,"(Ref: "+ref+")"]))
				else:
					if set([url]).issubset(self.sitecontent | self.skipped):
						logging.info("%d\t%s\tUnknown HTML\t%s\t(Ref: %s)",resp.status,resp.reason,url,ref)
						if not self.quiet:
							if self.verbose or self.withcontent:
								print("\t".join([str(self.urlmeta[url]['status']),self.urlmeta[url]['reason'],"*Un/cont*",url,"(Ref: "+ref+")"]))
					else:
						logging.info("%d\t%s\tUnknown Content\t%s\t(Ref: %s)",resp.status,resp.reason,url,ref)
						if not self.quiet:
							if self.verbose:
								print("\t".join([str(self.urlmeta[url]['status']),self.urlmeta[url]['reason'],"*Un/HTML*",url,"(Ref: "+ref+")"]))
			if set([url]).issubset(self.redirected):
				logging.info("%d\t%s\tRedirect\t%s => %s\t(Ref: %s)",resp.status,resp.reason,url,self.urlmeta[url]['location'],ref)
				if not self.quiet:
					if self.verbose:
						print("\t".join([str(self.urlmeta[url]['status']),self.urlmeta[url]['reason'],url,"=>",self.urlmeta[url]['location'],"(Ref: "+ref+")"]))
			if set([url]).issubset(self.notfound):
				logging.warning("%d\t%s\t%s\t(Ref: %s)",resp.status,resp.reason,url,ref)
				if not self.quiet:
					print("\t".join([str(self.urlmeta[url]['status']),self.urlmeta[url]['reason'],url,"(Ref: "+ref+")"]))
			if set([url]).issubset(self.errored):
				logging.warning("%d\t%s\t%s\t(Ref: %s)",resp.status,resp.reason,url,ref)
				if not self.quiet:
					print("\t".join([str(self.urlmeta[url]['status']),self.urlmeta[url]['reason'],url,"(Ref: "+ref+")"]))

	def code_2xx(self,url,URL,resp,ref,deep):
		mime = resp.getheader("Content-Type")
		logging.debug("[%s] Content type: %s",url,mime)

		self.successful.add(url)
		self.urlmeta[url]['mime'] = mime

		if re.search('^text/html', mime):
			self.mime_html(url,URL,resp,ref,deep)
		else:
			logging.info("[%s] OK. Skipping",url)
			self.skipped.add(url)

	def mime_html(self,url,URL,resp,ref,deep):
		html_page = resp.read()
		logging.debug("[%s] Parsing page",url)
		soup = BeautifulSoup(html_page,'html.parser')

		self.tags_a(url,URL,ref,deep,soup)

	def tags_a(self,url,URL,ref,deep,soup):
		logging.debug("[%s] Searching links",url)
		for link in soup.findAll("a"):
			href = link.get('href')
			P = urllib.parse.urlparse(href)._replace(params='',fragment='')
			if not self.extended:
				P = P._replace(query='')
			if isinstance(P,urllib.parse.ParseResult):
				pointer, P = self.prepare_url(P,url,URL)
				logging.debug("[%s] Found link %s",url,pointer)
				self.url(url,URL,ref,deep,P,pointer)

	def prepare_url(self,P,url,URL):
		if set([P.scheme]).issubset(set(['',])):
			P = P._replace(scheme=URL.scheme)

		if set([P.scheme]).issubset(set(['http','https'])):
			if P.netloc == '':
				P = P._replace(netloc=URL.netloc)
				res = re.match('\.(/.*)',P.path)
				if res:
					P = P._replace(path=res.group(1))

			if P.path.find("\n") >= 0:
				P = P._replace(path=P.path.replace("\n",""))
	
		return urllib.parse.urlunparse(P), P

	def url(self,url,URL,ref,deep,P,pointer):
		if not set([pointer]).issubset(self.processed):
			self.processed.add(pointer)
			if self.is_internal(P,url,URL):
				logging.debug("[%s] Internal link. Adding to queue",url)
				self.internal.add(pointer)
				self.push(pointer,url,deep+1)
			elif self.is_similar(P,url,self.domains):
				logging.debug("[%s] Internal crossdomain link. Adding to queue",url)
				self.crossdomain.add(pointer)
				self.push(pointer,url,deep+1)
			else:
				logging.debug("[%s] External link",url)
				self.external.add(pointer)

			if P.scheme in ('http','https') and P.scheme != URL.scheme:
				logging.debug("[%s] Crossprotocol link",url)
				self.crossprotocol.add(pointer)
				if set([pointer]).issubset(self.sitecontent):
					self.mixedcontent.add(pointer)
					logging.debug("[%s] Mixed content found",url)

	def is_internal(self,P,url,URL):
		urldomain = re.search('^(www\.)?(.*)$',URL.netloc).group(2)
		pointerdomain = re.search('^(www\.)?' + urldomain, P.netloc)
		return bool(pointerdomain)

	def is_similar(self,P,url,domains):
		res = False
		for d in domains:
			if re.search('^(www\.)?' + re.search('^(www\.)?(.*)$',d).group(2), P.netloc):
				res = True
				break
		return res

	def code_3xx(self,url,URL,resp,ref,deep):
		location = resp.getheader("Location");
		self.redirected.add(url)
		self.urlmeta[url]['location'] = location

		P = urllib.parse.urlparse(location)._replace(params='',fragment='')
		self.url(url,URL,ref,deep,P,location)

	def code_4xx(self,url,URL,resp,ref,deep):
		self.notfound.add(url)

	def code_5xx(self,url,URL,resp,ref,deep):
		self.errored.add(url)

class ConfigException(Exception):
	pass

if __name__ == "__main__":
	main = UT(sys.argv[1:])
