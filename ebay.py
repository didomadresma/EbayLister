import tinyxml
import urllib2

__XML_TMPL = {

'Base': [None, '''
<?xml version="1.0" encoding="utf-8" ?>
<Request xmlns="urn:ebay:apis:eBLBaseComponents">
<DetailLevel>ReturnAll</DetailLevel>
</Request>
''']
,

'GetItem': [None, '''
<?xml version="1.0" encoding="utf-8" ?>
<Request xmlns="urn:ebay:apis:eBLBaseComponents">
<DetailLevel>ReturnAll</DetailLevel>
<ItemID></ItemID>
<IncludeItemSpecifics></IncludeItemSpecifics>
</Request>
''']
,

'GetAllBidders': [None, '''
<?xml version="1.0" encoding="utf-8" ?>
<Request xmlns="urn:ebay:apis:eBLBaseComponents">
<DetailLevel>ReturnAll</DetailLevel>
<ItemID></ItemID>
<CallMode>ViewAll</CallMode>
<IncludeBiddingSummary>false</IncludeBiddingSummary>
</Request>
''']
,

'UploadSiteHostedPictures': [None, '''
<?xml version="1.0" encoding="utf-8" ?>
<Request xmlns="urn:ebay:apis:eBLBaseComponents">
<DetailLevel>ReturnAll</DetailLevel>
<ExternalPictureURL></ExternalPictureURL>
<PictureSet>Supersize</PictureSet>
</Request>
''']
,

}

def get_xml_tmpl(method):
    tmpl = __XML_TMPL.get(method)
    if tmpl[0] == None: tmpl[0] = tinyxml.loads(tmpl[1])
    return tmpl[0].copy()

class Ebay:
    def __init__(self, devid, appid, certid, token, server, level=767, **kwargs):
        self.devid = devid
        self.appid = appid
        self.certid = certid
        self.token = token
        self.server = server
        self.level = level
    
    def call(self, method, xml):
        hdrs = {
            "X-EBAY-API-COMPATIBILITY-LEVEL": str(self.level),
            "X-EBAY-API-DEV-NAME": self.devid,
            "X-EBAY-API-APP-NAME": self.appid,
            "X-EBAY-API-CERT-NAME": self.certid,
            "X-EBAY-API-CALL-NAME": method,
            "X-EBAY-API-SITEID": '0',
        }
        xml['RequesterCredentials']['eBayAuthToken'] = self.token
        f = urllib2.urlopen(urllib2.Request(self.server, xml.asxml(method + 'Request'), hdrs))
        return tinyxml.loads( f.read() )
    
    def GetItem(self, itemid, inclspec=True):
        method = 'GetItem'
        xml = get_xml_tmpl(method)
        xml['ItemID'] = itemid
        xml['IncludeItemSpecifics'] = inclspec and 'true' or 'false'
        
        return self.call(method, xml)
        
    def GetAllBidders(self, itemid, inclsummary):
        method = 'GetAllBidders'
        xml = get_xml_tmpl(method)
        xml['ItemID'] = itemid
        xml['IncludeBiddingSummary'] = inclsummary and 'true' or 'false'
        
        return self.call(method, xml)

    def UploadSiteHostedPictures(self, pic_url):
        method = 'UploadSiteHostedPictures'
        xml = get_xml_tmpl(method)
        xml['ExternalPictureURL'] = pic_url
        
        return self.call(method, xml)
    
    