import sys
import os
import json
import re
import ConfigParser
import Queue
import thread
import traceback
import urllib
import hashlib
import math
import cStringIO
import tinyxml
import Image, ImageDraw, ImageFont
from mako import lookup
import wx
import wx.grid as grid
import wx.lib.gridmovers as gridmovers
import category
import ebay
import webbrowser

def parseNumber(s):
    try:
        n = float(s)
    except Exception, e:
        n = 0.0
    return n

def get_bitmap(fnz, w=120, h=120):
    try:
        return wx.Image(fnz, wx.BITMAP_TYPE_JPEG).Scale(w, h).ConvertToBitmap()
    except:
        return None

class BitmapRenderer(grid.PyGridCellRenderer):
    def Draw(self, gd, attr, dc, rect, row, col, is_selected):
        dc.DrawBitmap(gd.GetTable().data[row][col][1], rect.X, rect.Y)
        

class CustomDataTable(grid.PyGridTableBase):
    def __init__(self, hdrs=[], data=[]):
        grid.PyGridTableBase.__init__(self)
        self.hdrs = hdrs
        self.data = data
        
    def GetColLabelValue(self, col):
        return self.hdrs[col][0]
    
    def GetNumberRows(self):
        return len(self.data)
    
    def GetNumberCols(self):
        return len(self.hdrs)
    
    def IsEmptyCell(self, row, col):
        return not self.data[row][col]
    
    def GetValue(self, row, col):
        return self.data[row][col]
    
    def SetValue(self, row, col, value):
        self.data[row][col] = value
    
    def MoveColumn(self, frm, to):
        return
    
    def MoveRow(self, frm, to):
        if not self.data or frm == to: return
        gv = self.GetView()
        
        if gv:
            d = self.data.pop(frm)
            if to > frm:
                self.data.insert(to - 1, d)
            else:
                self.data.insert(to, d)
            
            gv.BeginBatch()
            msg = grid.GridTableMessage(self, grid.GRIDTABLE_NOTIFY_ROWS_INSERTED, to, 1)
            gv.ProcessTableMessage(msg)
            msg = grid.GridTableMessage(self, grid.GRIDTABLE_NOTIFY_ROWS_DELETED, frm, 1)
            gv.ProcessTableMessage(msg)
            gv.EndBatch()


class DragableGrid(grid.Grid):
    def __init__(self, parent, ID):
        grid.Grid.__init__(self, parent, -1)
        
        gridmovers.GridColMover(self)
        self.Bind(gridmovers.EVT_GRID_COL_MOVE, self.OnColMove, self)
        
        gridmovers.GridRowMover(self)
        self.Bind(gridmovers.EVT_GRID_ROW_MOVE, self.OnRowMove, self)

    def OnColMove(self, evt):
        frm = evt.GetMoveColumn()
        to = evt.GetBeforeColumn()
        self.GetTable().MoveColumn(frm, to)
    
    def OnRowMove(self,evt):
        frm = evt.GetMoveRow()
        to = evt.GetBeforeRow()
        self.GetTable().MoveRow(frm, to)
    

class ConfigDialog(wx.Dialog):
    def __init__(self, parent, cfg, cate):
        wx.Dialog.__init__(self, parent, wx.ID_ANY, "config", None, (500, 300))
        self.SetFont(wx.Font(12, wx.DEFAULT, wx.wx.NORMAL, wx.wx.NORMAL))

        msz = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(msz)
        
        sz = wx.GridBagSizer(5, 5)
        msz.Add(sz, 0, wx.EXPAND|wx.ALL, 10)
        
        self.cfg = cfg
        self.optwid = wid = {}
        i = 0
        sps = {'type': cate['type'].keys(), 'name': [], 'duration': ['30', '7', '14']}
        sps.update(cate['specifics'])
        for k, v in sps.items():
            if type(v) != list:
                cfg[k] = v
                continue
            
            sz.Add(wx.StaticText(self, wx.ID_ANY, k + ': ', (50, -1)), (i, 0), flag=wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT)
            w = wid[ k ] = wx.ComboBox(self, wx.ID_ANY, cfg.get(k, v and v[0] or ''), size=(200,-1), choices=v)
            sz.Add(w, (i, 1), flag=wx.EXPAND)
            i += 1
        
        msz.Fit(self)
        
    def ShowModal(self):
        ret = wx.Dialog.ShowModal(self)
        
        for k, v in self.optwid.items():
            self.cfg[k] = v.GetValue()
            
        return ret


class ProgressDialog(wx.Dialog):
    def __init__(self, parent):
        wx.Dialog.__init__(self, parent, wx.ID_ANY, "Loading", None, (500, 200))
        self.SetFont(wx.Font(12, wx.DEFAULT, wx.wx.NORMAL, wx.wx.NORMAL))

        msz = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(msz)

        self.txt_log = wx.TextCtrl(self, wx.ID_ANY, size=(500, 300), style=wx.TE_MULTILINE|wx.TE_READONLY)
        msz.Add(self.txt_log, 1, wx.EXPAND|wx.ALL, 10)
        
        self.btn_continue = wx.Button(self, wx.ID_ANY, "Continue")
        msz.Add(self.btn_continue, 0, wx.ALL^wx.TOP|wx.ALIGN_CENTER_HORIZONTAL, 10)
        self.btn_continue.Bind(wx.EVT_BUTTON, self.btn_continue_click)
        
        msz.Fit(self)

    def btn_continue_click(self, evt):
        self.Parent.load_to_ebay(self.mode)

    def reset(self):
        self.txt_log.Clear()
        self.btn_continue.Disable()

    def log(self, s):
        self.txt_log.WriteText(s)

    def enable_next(self):
        self.btn_continue.Enable()


class MyFrame(wx.Frame):
    rx_space = re.compile('\s+', re.S|re.I|re.M)
    
    grid_hdrs = [
        ('Image', 120),
        ('Name', 320),
        ('Price', 80),
        ('XS', 50),
        ('S', 50),
        ('M', 50),
        ('L', 50),
        ('XL', 50),
        ('XXL', 50)
    ]
    
    def __init__(self):
        self.data_tbl = CustomDataTable(self.grid_hdrs)
        self.init_widget()
        
        self.dirpath = None
        self.dirlist = []
        
        self.jsdata = {}
        self.cate = None
        self.load_cates()
        
        #self.btn_load_click(None)
        #self.cbb_loaddir.SetSelection(0)
        #self.cbb_loaddir_select(None)
        
        self.loading_status = 0
        
        self.prgdlg = ProgressDialog(self)
    
    def load_cates(self):
        self.cbb_cate.SetItems(g_cates.keys())
    
    def btn_load_click(self, evt):
        #dirpath = r'E:\in' #None
        dirpath = None
        dlg = wx.DirDialog(self, "Choose a directory:", style=wx.DD_DEFAULT_STYLE|wx.DD_DIR_MUST_EXIST)
        if dlg.ShowModal() == wx.ID_OK: dirpath = dlg.GetPath()
        dlg.Destroy()
        if not dirpath: return
        
        dirlist = []
        for d in sorted(os.listdir(dirpath)):
            dd = os.path.join(dirpath, d)
            if os.path.isdir(dd) and os.listdir(dd):
                dirlist.append(d)
                
        self.dirpath = dirpath
        self.dirlist = dirlist
        self.cbb_loaddir.SetItems(dirlist)
        self.cbb_cate.SetSelection(-1)
        
    def refresh_grid(self):
        self.dgrid_pics.SetTable(self.data_tbl)
        for i in range(len(self.grid_hdrs)):
            self.dgrid_pics.SetColSize(i, self.grid_hdrs[i][1])
        self.dgrid_pics.ForceRefresh()
    
    def cbb_cate_select(self, evt):
        self.jsdata['config'] = {}
        cate = self.cate = g_cates.get(self.cbb_cate.GetValue(), None)
        if cate == None: return
        
        if not self.txt_title.GetValue().strip():
            self.btn_gentitle_click(None)
        
        s = cate['shipping']
        self.txt_shipping0.SetValue(s[0])
        self.txt_shipping1.SetValue(s[1])
        self.txt_shipping2.SetValue(s[2])
        self.txt_shipping3.SetValue(s[3])
    
    def cbb_loaddir_select(self, evt):
        self.dgrid_pics.SetFocus()
        
        idx = self.cbb_loaddir.GetCurrentSelection()
        self.cur_img_dir = d = os.path.join(self.dirpath, self.dirlist[idx])
        
        jf = os.path.join(d, 'config.dat')
        js = {}
        if os.path.isfile(jf):
            try:
                js = json.load(open(jf, 'rb')) or {}
            except Exception, e:
                js = {}
        
        self.jsdata = js
        self.txt_title.SetValue(js.get('title', ''))
        self.txt_desc.SetValue(js.get('desc', ''))
        self.txt_shipping0.SetValue(js.get('shipping', ''))
        self.txt_shipping1.SetValue(js.get('shipping_add', ''))
        self.txt_shipping2.SetValue(js.get('intl_shipping', ''))
        self.txt_shipping3.SetValue(js.get('intl_shipping_add', ''))
        
        cnz = js.get('cate', '')
        self.cate = g_cates.get(cnz, None)
        if self.cate != None:
            self.cbb_cate.SetSelection( self.cbb_cate.GetItems().index(cnz) )
        else:
            self.cbb_cate.SetSelection(-1)
        
        js.setdefault('config', {})
        self.cbb_cover.SetSelection(js.get('cover_image', -1))
        
        data_d = {}
        k = 0
        for r in js.get('data', []):
            if os.path.isfile( os.path.join(d, r[0]) ):
                data_d[r[0]] = (r, k)
                k += 1
        
        for f in sorted(os.listdir(d), key=lambda x:x.lower()):
            f = f.lower()
            if f[-4:] != '.jpg': continue
            if not data_d.has_key(f):
                data_d[f] = ([ unicode(f), u'', u'', u'', u'', u'', u'', u'', u'' ], k)
                k += 1
        
        data = []
        for r in sorted(data_d.values(), key=lambda x: x[1]):
            r = r[0]
            bmp = get_bitmap(os.path.join(d, r[0]))
            if bmp == None: continue
            r[0] = (r[0], bmp)
            data.append(r)
        
        self.img_cache = {}
        self.data_tbl.data = data
        self.refresh_grid()
        
    def update_jsdata(self):
        js = self.jsdata
        
        js['cate'] = self.cbb_cate.GetValue()
        
        js['title'] = self.txt_title.GetValue().strip()
        js['desc'] = self.txt_desc.GetValue().strip()
        
        js['shipping'] = self.txt_shipping0.GetValue().strip()
        js['shipping_add'] = self.txt_shipping1.GetValue().strip()
        js['intl_shipping'] = self.txt_shipping2.GetValue().strip()
        js['intl_shipping_add'] = self.txt_shipping3.GetValue().strip()
        
        js['cover_image'] = self.cbb_cover.GetCurrentSelection()
        
        js['data'] = [[d[0][0]] + map(unicode.strip, d[1:]) for d in self.data_tbl.data ]
    
    def btn_save_click(self, evt):
        idx = self.cbb_loaddir.GetCurrentSelection()
        if idx < 0: return
        
        self.update_jsdata()
        json.dump(self.jsdata, open(os.path.join(self.dirpath, self.dirlist[idx], 'config.dat'), 'wb'))
    
    def btn_config_click(self, evt):
        if self.cate == None: return
        dlg = ConfigDialog(self, self.jsdata['config'], self.cate)
        dlg.ShowModal()
        dlg.Destroy()
    
    def get_info(self):
        colors = set()
        sizes = set()
        for r in self.jsdata['data']:
            c = r[1].strip()
            if c:
                colors.add(c)
                for i in range(3, len(r)):
                    s = r[i].strip()
                    if s.isdigit() and int(s): sizes.add(self.grid_hdrs[i][0])

        return (colors, sizes)
    
    def get_title(self):
        s = self.jsdata['config']
        
        ds = self.get_info()
        color_s = ' '.join(sorted(ds[0]))
        size_s = ' '.join(sorted(ds[1]))
        
        title = self.cate['title'] % {"Brand":s.get('Brand', ''), "Style":s.get('Style', ''), "type":s.get('type', ''), "name":s.get('name', ''), "colors":color_s, "sizes":size_s}
        title = self.rx_space.sub(' ', title)
        if len(title) > 80:
            title = self.cate['title'] % {"Brand":s.get('Brand', ''), "Style":s.get('Style', ''), "type":s.get('type', ''), "name":s.get('name', ''), "colors":"", "sizes":size_s}
            title = self.rx_space.sub(' ', title)
            if len(title) > 80:
                title = self.cate['title'] % {"Brand":s.get('Brand', ''), "Style":s.get('Style', ''), "type":s.get('type', ''), "name":s.get('name', ''), "colors":color_s, "sizes":""}
                title = self.rx_space.sub(' ', title)
                if len(title) > 80:
                    title = self.cate['title'] % {"Brand":s.get('Brand', ''), "Style":s.get('Style', ''), "type":s.get('type', ''), "name":s.get('name', ''), "colors":"", "sizes":""}
                    title = self.rx_space.sub(' ', title)[:80]
                    
        return title.upper()
    
    def btn_gentitle_click(self, evt):
        if self.cate == None: return
        self.update_jsdata()
        self.txt_title.SetValue( self.get_title() )
    
    def md5img(self, fnz, s):
        h = hashlib.md5(s)
        fd = open(fnz, 'rb')
        while True:
            d = fd.read(4096)
            if not d: break
            h.update(d)
        return h.hexdigest()
    
    def upload(self, mode='test', verify=True):
        try:
            self.log("loading mode - %s - verify: %s" % (mode, verify) )
            if self._upload(mode, verify) == True and verify:
                self.enable_next()
        except Exception, e:
            self.log( traceback.format_exc() )
        finally:
            self.set_status(0)
            self.log('pause...')
    
    def _upload(self, mode='test', verify=True):
        self.update_jsdata()
        js = self.jsdata
        cfg = js['config']
        cate = self.cate
        
        var_count = 0
        for r in js['data']:
            if any(r[2:]): var_count += 1
        if not var_count: return
        
        eb = ebay.Ebay( **dict(g_config.items(mode)) )
        
        x = tinyxml.load(os.path.join(g_appdir, 'request.xml'))
        item = x['Item']
        item['title'] = js['title']
        if cfg.get('duration'): item['ListingDuration'] = 'Days_%s' % (cfg['duration'], )
        
        s0 = parseNumber(js['shipping'])
        s1 = parseNumber(js['shipping_add'])
        s2 = parseNumber(js['intl_shipping'])
        s3 = parseNumber(js['intl_shipping_add'])
        
        if s0:
            item['ShippingDetails']['ShippingServiceOptions']['ShippingServiceCost'] = s0
            if s1:
                item['ShippingDetails']['ShippingServiceOptions']['ShippingServiceAdditionalCost'] = s1
        else:
            item['ShippingDetails']['ShippingServiceOptions']['FreeShipping'] = 'true';
        
        if s2:
            item['ShipToLocations'] = 'Worldwide'
            item['ShippingDetails']['InternationalShippingServiceOption']['ShippingServiceCost'] = s2
            if s3:
                item['ShippingDetails']['InternationalShippingServiceOption']['ShippingServiceAdditionalCost'] = s3
        else:
            del item['ShippingDetails']['InternationalShippingServiceOption']
        
        item['PayPalEmailAddress'] = g_config.get(mode, 'paypal', '')
        item['PrimaryCategory']['CategoryID'] = cate['type'][ cfg['type'] ]
        
        nvls = item['ItemSpecifics']['NameValueList']
        for k in cate['specifics'].keys():
            nvl = nvls[ len(nvls) ]
            nvl['Name'] = k
            nvl['Value'] = cfg[k]
        
        vas = item['Variations']
        vss = vas['VariationSpecificsSet']
        vps = vas['Pictures']['VariationSpecificPictureSet']
        var = vas['Variation']
        
        color_n = vss['NameValueList'][0]['Name'].val
        size_n = vss['NameValueList'][1]['Name'].val = u"Size (%s's)" % (cfg['type'].capitalize(), )
        color_v = vss['NameValueList'][0]['Value']
        size_v = vss['NameValueList'][1]['Value']
        
        upa = g_config.getint('image', 'ebay-upload-all')
        imq = g_config.getint('image', 'quality')
        srv = g_config.get('image', 'server')
        ims = map(int, g_config.get('image', 'size').split('x', 1))
        hdr = {'Content-Type': 'application/octet-stream'}
        img_cache = self.img_cache
        
        szl = [0] * 6
        pus = item['PictureDetails']['PictureURL']
        k = 0
        rc = None
        mpics = []
        for i in range( len(js['data']) ):
            if self.loading_status == 1: return
            
            r = js['data'][i]
            ffnz = os.path.join(g_frame.cur_img_dir, r[0])
            pt = 0
            if any(r[2:]):
                pt = 2
                rc = r
                color = (u'%s %02d' % (r[1].upper(), k + 1)).strip()
                mpics.append( (color, ffnz, r[0]) )
                k += 1
                color_v[ len(color_v) ] = color
                vsp = vps[ len(vps)]
                pus = vsp['PictureURL']
                vsp['VariationSpecificValue'] = color
                for c in range(3, 9):
                    if not r[c]: continue
                    szl[c - 3] += 1
                    v = var[ len(var) ]
                    v['SKU'] = u'%s_%s' % (color.replace(' ', '_'), self.grid_hdrs[c][0])
                    v['Quantity'] = r[c]
                    v['StartPrice'] = r[2]
                    v['StartPrice'].attr('currencyID', 'USD')
                    vl = v['VariationSpecifics']['NameValueList']
                    vl[0]['Name'] = color_n
                    vl[0]['Value'] = color
                    vl[1]['Name'] = size_n
                    vl[1]['Value'] = self.grid_hdrs[c][0]
                    
            elif upa or js['cover_image'] >= 1 and i == 0:
                pt = 1
                
            ic = img_cache.setdefault(r[0], {})
            if pt == 2 and var_count > 1:
                md5 = self.md5img(ffnz, color)
            else:
                md5 = self.md5img(ffnz, '')
            if ic.get('md5') != md5:
                ic.clear()
                ic['md5'] = md5
            
            alt = ic.get('alt')
            if not alt:
                im = Image.open(ffnz)
                im.thumbnail(ims, Image.ANTIALIAS)
                
                if pt == 2 and var_count > 1:
                    dw = ImageDraw.Draw(im)
                    txt = color
                    for fs in (60, 48, 36, 24, 18):
                        font = ImageFont.truetype(g_font_fnz, fs)
                        w, h = dw.textsize(txt, font=font)
                        if w <= im.size[0]: break
                    dw.text( ( (im.size[0] - w) / 2 , 5 ), txt, '#cfa31e', font )
                
                fd = cStringIO.StringIO()
                im.save(fd, "JPEG", quality=imq)
                im = None
                
                self.log( u"uploading[%s / %s] %s" % (i + 1, len(js['data']), r[0]) )
                ic['alt'] = alt = urllib.urlopen(srv, fd.getvalue()).read().strip()
                if not alt: return
            
            if pt:
                if not ic.get(mode):
                    self.log("copying to ebay " + r[0])
                    eb_res = eb.UploadSiteHostedPictures(alt)
                    fullurl = ic[mode] = eb_res['SiteHostedPictureDetails']['FullURL']
                    if not fullurl:
                        self.log( eb_res['Errors']['LongMessage'] )
                        return
                pus[ len(pus) ] = ic[mode]
        
        if self.loading_status == 1: return
        
        """
        if var_count == 1:
            oc = OfficialColors.get(rc[1].lower())
            if oc:
                nvl = nvls[ len(nvls) ]
                nvl['Name'] = 'Color'
                nvl['Value'] = oc
        """
        
        if var_count > 1 and js['cover_image'] < 1:
            md5 = hashlib.md5()
            for i in range( len(mpics) ): md5.update( img_cache[ mpics[i][2] ]['md5'] )
            md5 = md5.hexdigest()
            cvimg = img_cache.setdefault('"cover_image"', {})
            if md5 != cvimg.get('md5'):
                cvimg.clear()
                cvimg['md5'] = md5
            
            alt = cvimg.get('alt')
            if not alt:
                xc = int(math.ceil(var_count ** 0.5))
                yc = int(math.ceil(var_count / float(xc)))
                im = Image.new("RGB", (xc * 700, yc * 700))
                dw = ImageDraw.Draw(im)
                for i in range( len(mpics) ):
                    m = mpics[i]
                    sim = Image.open( m[1] )
                    sim.thumbnail( (700, 700), Image.ANTIALIAS)
                    sw, sh = sim.size
                    dm = divmod(i, xc)
                    sx = dm[1] * 700
                    sy = dm[0] * 700
                    im.paste(sim, ( sx + (700 - sw) / 2, sy + (700 - sh) / 2 ) )
                    
                    txt = m[0]
                    for fs in (60, 48, 36, 24, 18):
                        font = ImageFont.truetype(g_font_fnz, fs)
                        w, h = dw.textsize(txt, font=font)
                        if w <= 700: break
                    dw.text( ( sx + (700 - w) / 2 , sy + 5 ), txt, '#cfa31e', font )
                
                fd = cStringIO.StringIO()
                im.save(fd, "JPEG", quality=imq)
                im = None
            
                self.log("uploading cover image")
                cvimg['alt'] = alt = urllib.urlopen(srv, fd.getvalue()).read().strip()
                if not alt: return
            
            cover_img = cvimg.get(mode)
            if not cover_img:
                self.log("copying cover image to ebay")
                eb_res = eb.UploadSiteHostedPictures(alt)
                cvimg[mode] = cover_img = eb_res['SiteHostedPictureDetails']['FullURL']
                if not cover_img:
                    self.log( eb_res['Errors']['LongMessage'] )
                    return
        
        elif js['cover_image'] >= 1:
            cover_img = img_cache[ js['data'][0][0] ][mode]
        
        else:
            cover_img = img_cache[ rc[0] ][mode]
        
        item['PictureDetails']['GalleryURL'] = cover_img
        item['PictureDetails']['PictureURL'] = cover_img
        
        for c in range( len(szl) ):
            if szl[c]: size_v[ len(size_v) ] = self.grid_hdrs[c + 3][0]
        
        for t in (js['cate'] + '.html', cate.get('desc_tmpl', 'default.html'), 'default.html'):
            if g_desc_tmpl.has_template(t):
                item['Description'] = g_desc_tmpl.get_template(t).render_unicode(js=js, cfg=cfg, img=img_cache).strip()
                break
        
        open(os.path.join(g_appdir, "_request.xml"), 'wb').write( x.asxml() )
        
        if self.loading_status == 1: return
        
        self.log("loading to ebay")
        s = eb.call( (verify and 'Verify' or '') + 'AddFixedPriceItem', x )
        if s['Ack'].val.lower() != 'success':
            self.log( s['Errors']['LongMessage'] )
        else:
            itemid = s['ItemID'].val
            self.log( 'ItemID: ' + itemid )
            for f in s['Fees']['Fee']:
                if f['Name'].val.lower() == 'listingfee':
                    self.log( 'ListingFee[%s]: %s' % (mode, f['Fee']) )
                    break
                
            if int(itemid): webbrowser.open( EbayItemUrl[mode] % (itemid, ) )
        
        return True
        
    def log(self, s):
        wx.CallAfter( self.prgdlg.log, unicode(s) + u"\n" )
        
    def enable_next(self):
        wx.CallAfter( self.prgdlg.enable_next )
    
    def _set_status(self, sts):
        self.loading_status = sts
        
    def set_status(self, sts):
        wx.CallAfter(self._set_status, sts)
    
    
    def preload_to_ebay(self, mode):
        if self.cate == None: return
        if self.loading_status == 2:
            self.loading_status = 1
            return
        if self.loading_status != 0: return
        
        self.loading_status = 2
        self.prgdlg.reset()
        self.prgdlg.mode = mode
        g_qwork.put( {'func': self.upload, 'args':(mode, True), 'kwargs': {}} )
        self.prgdlg.ShowModal()
        if self.loading_status == 2:
            self.loading_status = 1
            
    def load_to_ebay(self, mode):
        if self.loading_status == 2:
            self.loading_status = 1
            return
        if self.loading_status != 0: return
        self.loading_status = 2
        g_qwork.put( {'func': self.upload, 'args':(mode, False), 'kwargs': {}} )
        
    
    def btn_test_click(self, evt):
        self.preload_to_ebay('test')
        
    def btn_upload_click(self, evt):
        self.preload_to_ebay('prod')
    
    def init_widget(self):
        wx.Frame.__init__(self, None, wx.ID_ANY, "Ebay Lister", None, (960, 800))
        self.SetFont(wx.Font(12, wx.DEFAULT, wx.wx.NORMAL, wx.wx.NORMAL))
        self.SetBackgroundColour("#F0F0F0")
        
        #
        self.panel_ctrl = wx.Panel(self, wx.ID_ANY)
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.panel_ctrl.SetSizer(sizer)
        
        self.btn_load = wx.Button(self.panel_ctrl, wx.ID_ANY, "Load")
        sizer.Add(self.btn_load, 0, wx.EXPAND)
        self.btn_load.Bind(wx.EVT_BUTTON, self.btn_load_click)
        
        self.cbb_loaddir = wx.ComboBox(self.panel_ctrl, wx.ID_ANY, "", None, (300, -1), style=wx.CB_READONLY)
        sizer.Add(self.cbb_loaddir, 0, wx.EXPAND|wx.LEFT, 5)
        self.cbb_loaddir.Bind(wx.EVT_COMBOBOX, self.cbb_loaddir_select)
        
        self.cbb_cate = wx.ComboBox(self.panel_ctrl, wx.ID_ANY, "", None, (220, -1), style=wx.CB_READONLY)
        sizer.Add(self.cbb_cate, 0, wx.EXPAND|wx.LEFT, 5)
        self.cbb_cate.Bind(wx.EVT_COMBOBOX, self.cbb_cate_select)
        
        self.btn_config = wx.Button(self.panel_ctrl, wx.ID_ANY, "Config")
        sizer.Add(self.btn_config, 0, wx.EXPAND|wx.LEFT, 5)
        self.btn_config.Bind(wx.EVT_BUTTON, self.btn_config_click)
        
        self.btn_test = wx.Button(self.panel_ctrl, wx.ID_ANY, "Test")
        sizer.Add(self.btn_test, 0, wx.EXPAND|wx.LEFT, 5)
        self.btn_test.Bind(wx.EVT_BUTTON, self.btn_test_click)
        
        self.btn_upload = wx.Button(self.panel_ctrl, wx.ID_ANY, "Upload")
        sizer.Add(self.btn_upload, 0, wx.EXPAND|wx.LEFT, 5)
        self.btn_upload.Bind(wx.EVT_BUTTON, self.btn_upload_click)
        
        self.btn_save = wx.Button(self.panel_ctrl, wx.ID_ANY, "Save")
        sizer.Add(self.btn_save, 0, wx.EXPAND|wx.LEFT, 5)
        self.btn_save.Bind(wx.EVT_BUTTON, self.btn_save_click)
        
        #
        self.panel_info = wx.Panel(self, wx.ID_ANY)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.panel_info.SetSizer(sizer)
        
        sz = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(sz, 0, wx.EXPAND)
        
        self.txt_title = wx.TextCtrl(self.panel_info, wx.ID_ANY, "Title..")
        self.txt_title.SetMaxLength(80)
        sz.Add(self.txt_title, 1, wx.EXPAND)
        
        self.btn_gentitle = wx.Button(self.panel_info, wx.ID_ANY, "Gen")
        sz.Add(self.btn_gentitle, 0, wx.EXPAND|wx.LEFT, 5)
        self.btn_gentitle.Bind(wx.EVT_BUTTON, self.btn_gentitle_click)
        
        self.txt_desc = wx.TextCtrl(self.panel_info, wx.ID_ANY, "Desc..", style=wx.TE_MULTILINE, size=(-1, 70))
        sizer.Add(self.txt_desc, 0, wx.EXPAND|wx.TOP, 5)
        
        sz = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(sz, 0, wx.EXPAND|wx.TOP, 5)
        
        sz.Add(
            wx.StaticText(self.panel_info, wx.ID_ANY, "Shipping: ", (20, -1)),
            0, wx.ALIGN_CENTER_VERTICAL
        )
        self.txt_shipping0 = wx.TextCtrl(self.panel_info, wx.ID_ANY, size=(60, -1))
        sz.Add(self.txt_shipping0, 0, wx.EXPAND|wx.LEFT, 5)
        self.txt_shipping1 = wx.TextCtrl(self.panel_info, wx.ID_ANY, size=(60, -1))
        sz.Add(self.txt_shipping1, 0, wx.EXPAND|wx.LEFT, 5)
        
        
        sz.Add(
            wx.StaticText(self.panel_info, wx.ID_ANY, "International-Shipping: ", (20, -1)),
            0, wx.ALIGN_CENTER_VERTICAL|wx.LEFT, 15
        )
        self.txt_shipping2 = wx.TextCtrl(self.panel_info, wx.ID_ANY, size=(60, -1))
        sz.Add(self.txt_shipping2, 0, wx.EXPAND|wx.LEFT, 5)
        self.txt_shipping3 = wx.TextCtrl(self.panel_info, wx.ID_ANY, size=(60, -1))
        sz.Add(self.txt_shipping3, 0, wx.EXPAND|wx.LEFT, 5)
        
        sz.Add(
            wx.StaticText(self.panel_info, wx.ID_ANY, "Cover-Image: ", (20, -1)),
            0, wx.ALIGN_CENTER_VERTICAL|wx.LEFT, 15
        )
        self.cbb_cover = wx.ComboBox(self.panel_info, wx.ID_ANY, "", None, (100, -1), ['Default', 'Image #1'], style=wx.CB_READONLY)
        sz.Add(self.cbb_cover, 0, wx.EXPAND|wx.LEFT, 5)
        
        #
        self.dgrid_pics = DragableGrid(self, wx.ID_ANY)
        self.dgrid_pics.SetDefaultRowSize(120)
        self.dgrid_pics.SetDefaultCellAlignment(wx.ALIGN_CENTER, wx.ALIGN_CENTER)
        
        self.refresh_grid()
        
        attr = grid.GridCellAttr()
        attr.SetReadOnly()
        attr.SetRenderer(BitmapRenderer())
        self.dgrid_pics.SetColAttr(0, attr)
        
        #
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.panel_ctrl, 0, wx.EXPAND|wx.ALL, 5)
        sizer.Add(self.panel_info, 0, wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, 5)
        sizer.Add(self.dgrid_pics, 1, wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, 5)
        
        self.SetSizer(sizer)
        

EbayItemUrl = {
    'test': u'http://cgi.sandbox.ebay.com/%s',
    'prod': u'http://www.ebay.com/itm/%s'
}

OfficialColors = {
    "beige": "Beiges",
    "black": "Blacks",
    "blue": "Blues",
    "brown": "Browns",
    "grey": "Grays",
    "green": "Greens",
    "ivory": "Ivories",
    "metallic": "Metallics",
    "multi-color": "Multi-color",
    "orange": "Oranges",
    "pink": "Pinks",
    "purple": "Purples",
    "red": "Reds",
    "white": "Whites",
    "yellow": "Yellows"
}

def worker():
    while True:
        w = g_qwork.get()
        try:
            w['func'](*w['args'], **w['kwargs'])
        except Exception, e:
            print e
            traceback.print_exc()
        g_qwork.task_done()


##########################################
g_appdir = os.path.dirname(__file__)
g_cates = category.cates
g_config = ConfigParser.SafeConfigParser()
g_config.read(os.path.join(g_appdir, 'config.ini'))
g_desc_tmpl = lookup.TemplateLookup([os.path.join(g_appdir, 'desc_tmpl')], None, True, input_encoding='utf8', output_encoding='utf8')
g_font_fnz = os.path.join(g_appdir, g_config.get('image', 'font'))

g_qwork = Queue.Queue()
thread.start_new_thread(worker, ())

g_app = wx.App(False)
g_frame = MyFrame()
g_frame.Show(True)
g_app.MainLoop()

