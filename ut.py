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
	domains = set()
	starturl = None
	only_static = False
	external_static = False
	list_view = False
	showsummary = False
	deep = None
	threads = cpu_count()+1
	service_threads = 1

	withcrossprotocol = False

	withinternal = False
	withcrossdomain = False
	withexternal = False
	withunknown = False

	withmixedcontent = False

	withcontent = False
	withstatic = False
	withhtml = False

	withredirects = False
	withnotfound = False

	urlmeta = {}
	queue = set()
	processed = set()

	successful = set()
	redirected = set()
	notfound = set()
	errored = set()

	troubled = set()
	skipped = set()

	internal = set()
	external = set()

	crossdomain = set()
	crossprotocol = set()
	sitecontent = set()

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
				"with-notfound",

				"with-mixed",
				"mixed"
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
				self.withcrossdomain = True
			elif o in ("--with-external"):
				self.withexternal = True
			elif o in ("--with-unknown"):
				self.withunknown = True

			elif o in ("--with-mixed","--mixed"):
				self.withmixedcontent = True

			elif o in ("--with-content","--mixed"):
				self.withcontent = True
			elif o in ("--with-static"):
				self.withstatic = True
			elif o in ("--with-html"):
				self.withhtml = True

			else:
				assert False, "unhandled option"

		if len(args) > 0:
			for u in args:
				D = urllib.parse.urlparse(u)
				if D.scheme == '':
					domain = D.path
					self.domains.add(re.search('^(www\.)?(.*)$',domain).group(2))

					D = D._replace(scheme='http',netloc=D.path,path="")
					self.push(urllib.parse.urlunparse(D),'',0)
					self.internal.add(urllib.parse.urlunparse(D))

					D = D._replace(scheme='https')
					self.push(urllib.parse.urlunparse(D),'',0)
					self.internal.add(urllib.parse.urlunparse(D))

				elif set([D.scheme]).issubset(set(['http','https'])):
					domain = D.netloc
					self.domains.add(re.search('^(www\.)?(.*)$',domain).group(2))

					self.push(urllib.parse.urlunparse(D),'',0)
					self.internal.add(urllib.parse.urlunparse(D))

				else:
					logging.warning("Unsupported protocol %s",D.scheme)
					continue

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
		for domain in self.domains:
			self.domaindir = self.workdir + domain + "/"
			self.suredir(self.domaindir)

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
			sys.stdout.write("\r" + " "*120 + "\r\n" )
			sys.stdout.flush()
			if len(self.successful):
				logging.info("Success: %d",len(self.successful))
				logging.info("\tInternal: %d",len(self.successful & self.internal))
				logging.info("\tCrossdomain: %d",len(self.successful & self.crossdomain))
				logging.info("\tExternal: %d",len(self.successful & self.external))
				logging.info("\tUnknown: %d",len(self.successful & (self.internal | self.crossdomain | self.external)))
				print("Success: " + str(len(self.successful)))
				print("\tInternal: " + str(len(self.successful & self.internal)))
				print("\tCrossdomain: " + str(len(self.successful & self.crossdomain)))
				print("\tExternal: " + str(len(self.successful & self.external)))
				print("\tUnknown: " + str(len(self.successful - (self.internal | self.crossdomain | self.external))))

			if self.withmixedcontent and len(self.mixedcontent):
				logging.info("Mixed content: %d",len(self.mixedcontent))
				logging.info("\nSuccess: %d",len(self.success & self.mixedcontent))
				print("Mixed content: " + str(len(self.mixedcontent)))
				print("\tSuccess: " + str(len(self.success & self.mixedcontent)))

			if len(self.redirected):
				logging.info("Redirected: %d",len(self.redirected))
				print("Redirected: " + str(len(self.redirected)))

			if len(self.notfound):
				logging.info("Not Found: %d",len(self.notfound))
				print("Not Found: " + str(len(self.notfound)))

			if len(self.errored):
				logging.info("Errored: %d",len(self.errored))
				print("Errored: " + str(len(self.errored)))

			if len(self.troubled):
				logging.info("Troubled: %d",len(self.troubled))
				print("Troubled: " + str(len(self.troubled)))
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

			conn.request("GET", path)
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
					tags.append('Intr')
				elif set([url]).issubset(self.crossdomain):
					disp |= self.withcrossdomain or self.verbose
					descr.append('Crossdomain')
					tags.append('Cross')
				elif set([url]).issubset(self.external):
					disp |= self.withexternal or self.verbose
					descr.append('External')
					tags.append('Extr')
				else:
					disp |= self.verbose or self.withunknown
					descr.append('Unknown')
					tags.append('Unknown')

				if set([url]).issubset(self.sitecontent):
					disp |= self.withcontent or self.verbose
					descr.append('Content')
					tags.append('Cont')
				elif set([url]).issubset(self.skipped):
					disp |= self.withstatic or self.verbose
					descr.append('Link')
					tags.append('Link')
				else:
					disp |= self.verbose or self.withhtml
					descr.append('HTML')
					tags.append('HTML')

				logging.info("%d\t%s\t|%s|\t%s\t(Ref: %s)",status,reason," ".join(descr),url,ref)
				if not self.quiet:
					if disp:
						print("\t".join([str(status),reason,"|" + "/".join(tags) + "|",url,"(Ref: "+ref+")"]))

			if set([url]).issubset(self.redirected):
				status = self.urlmeta[url]['status']
				reason = self.urlmeta[url]['reason']

				logging.info("%d\t%s\tRedirect\t%s => %s\t(Ref: %s)",status,reason,url,self.urlmeta[url]['location'],ref)
				if not self.quiet:
					if self.verbose or self.withredirects:
						print("\t".join([str(status),reason,url,"=>",self.urlmeta[url]['location'],"(Ref: "+ref+")"]))
			if set([url]).issubset(self.notfound):
				status = self.urlmeta[url]['status']
				reason = self.urlmeta[url]['reason']

				logging.warning("%d\t%s\t%s\t(Ref: %s)",status,reason,url,ref)
				if not self.quiet:
					if self.verbose or self.withnotfound:
						print("\t".join([str(status),reason,url,"(Ref: "+ref+")"]))
			if set([url]).issubset(self.errored):
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
