#!/usr/bin/python3

from bs4 import BeautifulSoup
from urllib.request import urlopen, Request
import urllib.parse
import http.client
import re, sys, os, getopt, time, pprint, datetime, base64, threading

class UT(object):
	"""docstring for UT"""

	verbose = False
	quiet = False
	extended = False
	domain = ""
	starturl = None
	logfile = None
	action = 'scan'
	only_static = False
	external_static = False
	list_view = False
	showsummary = False

	def read_params(self,mainargs):
		try:
			opts, args = getopt.getopt(mainargs, "hvqser:", ["help","verbose","quiet","diff","only-static","external-static","list"])
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
			elif o in ("--only-static"):
				self.only_static = True
			elif o in ("--external-static"):
				self.external_static = True
			elif o in ("--list"):
				self.list_view = True

			elif o in ("--diff"):
				self.action = "diff"
			else:
				assert False, "unhandled option"

		if self.action == "scan":
			if len(args) > 0:
				self.domain = args[0]
				if len(args) > 1:
					self.starturl = args[1]
			else:
				assert False, "wrong input parameters"
		elif self.action == "diff":
			if len(args) > 0:
				self.url = args[0]
		else:
			assert False, "unhandled action"

		global workdir
		workdir = str(os.path.expanduser("~")) + "/.ut/"
		try:
			os.stat(workdir)
		except:
			os.mkdir(workdir)

	def __init__(self, mainargs):
		try:
			self.read_params(mainargs)

			if self.action == "scan":
				self.scan()
			elif self.action == "diff":
				self.diff()
			else:
				assert False, "unhandled action"
		except SystemExit:
			pass
		except Exception as e:
			raise e
			print(e)

	def log(self,msg=[""],display_it = True):
		if display_it:
			sys.stdout.write("\t".join(msg) + "\n")
			sys.stdout.flush()
		self.logfile.write("\t".join(msg) + "\n")

	def display(self):
		while len(threading.enumerate())-2 > 0 or len(self.queue) > 0:
			sys.stdout.write("\rTreads: {0:2d}\tQueue: {1:4d}\tSucc: {2:4d}\tSkip: {3:4d}\tRedir: {4:4d}\tErr: {5:4d}".format(threading.active_count()-2,len(self.queue),len(self.successful),len(self.skipped),len(self.redirected),len(self.errored)))
			sys.stdout.flush()
			time.sleep(.5)

	def suredir(self,directory):
		try:
			os.stat(directory)
		except:
			os.mkdir(directory)	   

	def scan(self):
		global workdir, cachedir, domaindir

		domaindir = workdir + self.domain + "/"
		self.suredir(domaindir)

		cachedir = workdir + self.domain + "/cache/"
		self.suredir(cachedir)

		self.datesuffix = base64.b64encode(time.strftime("%Y-%m-%d %H:%M:%S").encode("ascii"))

		self.homeurl = "https://" + self.domain + "/"

		if self.starturl is None:
			self.starturl = self.homeurl

		self.visited = []
		self.visited_external = []
		self.queue = []
		self.successful = []
		self.skipped = []
		self.errored = []
		self.redirected = []

		self.logfile = open(domaindir + time.strftime("%Y%m%d%H%M%S") + ".log","w")
		if not self.list_view:
			self.log(["Domain:",self.domain])

		try:
			self.queue.append([self.starturl,''])
			main_thread = threading.main_thread()
			if self.quiet:
				mon_thread = threading.Thread(target=self.display)
				mon_thread.start()
			while len(self.queue):
				while threading.active_count()-2 < 12 and len(self.queue) > 0:
					url, ref = self.queue.pop()
					t = threading.Thread(target=self.chain, args=(url,ref))
					t.start()
				for t in threading.enumerate():
					if t is main_thread:
						continue
					if self.quiet:
						if t is mon_thread:
							continue
					t.join()
					break
		except KeyboardInterrupt:
			main_thread = threading.main_thread()
			for t in threading.enumerate():
				if t is main_thread:
					continue
				if self.quiet:
					if t is mon_thread:
						continue
				t.join()
			self.queue = []
			sys.stdout.write("\r" + " "*100 + "\rOperation Aborted\n")
			sys.stdout.flush()
			main_thread = threading.main_thread()
			for t in threading.enumerate():
				if t is main_thread:
					continue
				t.join()
		except:
			raise
		finally:
			sys.stdout.write("\r" + " "*100 + "\r" )
			sys.stdout.flush()
			if self.showsummary:
				if len(self.successful):
					self.log()
					self.log(["Success:"])
					for status, reason, url, ref in self.successful:
						self.log([str(status),reason,url,"(Ref:" + ref + ")"])
				if len(self.skipped):
					self.log()
					self.log(["Skipped:"])
					for status, reason, mime, url, ref in self.skipped:
						self.log([str(status),reason,mime,url,"(Ref:" + ref + ")"])
				if len(self.redirected):
					self.log()
					self.log(["Redirected:"])
					for status, reason, url, location, ref in self.redirected:
						self.log([str(status),reason,url,"=> " + location,"(Ref:" + ref + ")"])
				if len(self.errored):
					self.log()
					self.log(["Errored:"])
					for status, reason, url, ref in self.errored:
						self.log([str(status),reason,url,"(Ref:" + ref + ")"])
			self.log()
			if len(self.successful):
				self.log(["Success:",str(len(self.successful))])
			if len(self.skipped):
				self.log(["Skipped:",str(len(self.skipped))])
			if len(self.redirected):
				self.log(["Redirected:",str(len(self.redirected))])
			if len(self.errored):
				self.log(["Errored:",str(len(self.errored))])

	def chain(self,url,ref = ""):
		try:
			URL = urllib.parse.urlparse(url)

			if not isinstance(URL,urllib.parse.ParseResult):
				return

			URL = URL._replace(params='')
			URL = URL._replace(fragment='')
			URL = URL._replace(query='')

			url = urllib.parse.urlunparse(URL)

			if url not in self.visited:
				self.visited.append(url)

				if URL.scheme == 'http':
					conn = http.client.HTTPConnection(URL.netloc)
				elif URL.scheme == 'https':
					conn = http.client.HTTPSConnection(URL.netloc)
				else:
					return

				conn.request("GET", URL.path)
				resp = conn.getresponse()

				if resp.status in (200, ):
					mime = resp.getheader("Content-Type")
					if re.search('^text/html', mime):
						self.successful.append([resp.status,resp.reason,url,ref])
						if not self.quiet:
							self.log([str(resp.status),resp.reason,url,"(Ref:" + ref + ")"])
						html_page = resp.read()
						soup = BeautifulSoup(html_page,'html.parser')
						for link in soup.findAll("a"):
							P = urllib.parse.urlparse(link.get('href'))._replace(params='',fragment='',query='')
							if isinstance(P,urllib.parse.ParseResult):
								pointer = urllib.parse.urlunparse(P)
								if re.search('^(.*\.)?' + self.domain, P.netloc) and pointer not in self.visited and pointer not in self.queue:
									self.queue.append([pointer,url])
					else:
						self.skipped.append([resp.status,resp.reason,mime,url,ref])

				elif resp.status in (301, 302):
					location = resp.getheader("Location");
					self.redirected.append([resp.status,resp.reason,url,location,ref])
					self.queue.append([location,url])
					if not self.quiet and self.verbose:
						self.log([str(resp.status),resp.reason,url,"=> " + location,"(Ref:" + ref + ")"])

				elif resp.status in (500, ):
					self.errored.append([resp.status,resp.reason,url,ref])
				else:
					print(str(resp.status) + "\t" + resp.reason)
					return
		except KeyboardInterrupt:
			pass
		except http.client.BadStatusLine:
			self.errored.append(["ERROR","BadStatusLine",url,ref])
		except:
			raise

if __name__ == "__main__":
	main = UT(sys.argv[1:])
