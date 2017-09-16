#!/usr/bin/python3

from bs4 import BeautifulSoup
from urllib.request import urlopen, Request
import re, sys, os, getopt, time, pprint, datetime, base64

class UT(object):
	"""docstring for UT"""

	verbose = False
	quiet = False
	extended = False
	domain = ""
	starturl = None
	secured = False
	logfile = None

	def __init__(self, mainargs):
		try:
			opts, args = getopt.getopt(mainargs, "hvqd:u:es", ["--help","--verbose","--quiet","--domain","--start-url","--extended","--secured"])
		except getopt.GetoptError as err:
			print(err)
			sys.exit(2)

		for o, a in opts:
			if o in ("-v", "--verbose"):
				self.verbose = True
			elif o in ("-q", "--quiet"):
				self.quiet = True
			elif o in ("-e", "--extended"):
				self.extended = True
			elif o in ("-s", "--secured"):
				self.secured = True
			elif o in ("-h", "--help"):
				print("Help text coming soon")
				sys.exit()
			elif o in ("-u", "--start-url"):
				self.starturl = a
			else:
				assert False, "unhandled option"
		try:
			for d in args:
				self.parse(d,self.starturl)
		except KeyboardInterrupt:
			self.log()
			self.log("Operation Aborted")
			self.log("Success:\t" + str(successful))
			self.log("Warning:\t" + str(warned))
			self.log("Skipped:\t" + str(skipped))
			self.log("Errored:\t" + str(errored))
			self.log()
			pass
		except SystemExit:
			pass
		except Exception as e:
			raise e
			print(e)

	def log(self,msg="",display_it = True):
		if display_it:
			print(msg)
		self.logfile.write(msg + "\n")

	def parse(self,domain,starturl):
		home = str(os.path.expanduser("~"))
		workdir = home + "/.ut/"
		try:
			os.stat(workdir)
		except:
			os.mkdir(workdir)	   

		domaindir = workdir + domain + "/"
		try:
			os.stat(domaindir)
		except:
			os.mkdir(domaindir)	   

		datedir = domaindir + time.strftime("%Y-%m-%d") + "/"
		try:
			os.stat(datedir)
		except:
			os.mkdir(datedir)	   

		if self.secured:
			self.homeurl = "https://" + domain + "/"
		else:
			self.homeurl = "http://" + domain + "/"

		if self.starturl is None:
			self.starturl = self.homeurl

		self.visited = []
		self.successful = 0
		self.skipped = 0
		self.errored = 0
		self.warned = 0

		self.logfile = open(datedir + time.strftime("%H-%M-%S") + ".log","w")
		self.log("Domain: " + domain)
		self.log()

		self.chain(domain,self.starturl)

		self.log()
		self.log("Success:\t" + str(self.successful))
		self.log("Warning:\t" + str(self.warned))
		self.log("Skipped:\t" + str(self.skipped))
		self.log("Errored:\t" + str(self.errored))
		self.logfile.close()

	def chain(self,domain,url,ref = ""):
		urlu = url

		if not url:
			return

		m = re.match('^/([^/].*)', url)
		if m:
			url = self.homeurl + m.group(1)

		m = re.match("^(http|https)://([^/]+)/([^#]*)", url)
		if m and self.extended:
			url = m.group(1) + "://" + m.group(2) + "/" + m.group(3)
	 
		m = re.match("^(http|https)://([^/]+)/([^\?#]*)", url)
		if m and not self.extended:
			url = m.group(1) + "://" + m.group(2) + "/" + m.group(3)

		if url not in self.visited:
			self.visited.append(url)
			if re.search('^(http|https)://([^/]+\.)?' + domain + "/", url):

				if re.search('\.(jpg|png|pdf|jpeg|mp3|gif|eps)', url):
					self.visited.append(url)
					self.log("SKIP" + "\t" + url, verbose)
					self.skipped += 1
					return

				try:
					html = urlopen(Request(url, headers={'User-Agent': 'HadornBot/1.0'}))
					html_page = html.read()
					html_code = html.getcode()
	 
					if html_code == 200:
						self.log("OK" + "\t" + url, not self.quiet)
						self.successful += 1
					else:
						self.log("Status " + str(html_code) + "\t" + url)
						self.warned += 1

					soup = BeautifulSoup(html_page,'html.parser')
					for link in soup.findAll("a"):
						self.chain(domain,link.get('href'),url)

				except Exception as e:
					raise e
					self.log(str(e) + "\t" + url + "\t (Ref: " + ref + ")")
					self.errored += 1

if __name__ == "__main__":
	main = UT(sys.argv[1:])
