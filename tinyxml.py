from xml.sax.handler import ContentHandler
from xml.sax import parseString, saxutils

class SimpleXML_Iterator:
    def __init__(self, lst):
        self.__lst = lst
        self.__idx = 0
        
    def __iter__(self):
        return self
    
    def next(self):
        idx = self.__idx
        if idx >= len(self.__lst): raise StopIteration()
        self.__idx += 1
        return SimpleXML(_lst=[self.__lst[idx]])

class SimpleXML(object):
    
    def __init__(self, val=None, _lst=None, out_encoding='UTF-8', in_encoding='UTF-8'):
        self.out_encoding = out_encoding
        self.in_encoding = in_encoding
        self.__lst = []
        
        if val != None:
            if type(val) == list:
                for v in val: self.__lst.append(self.__node(v))
            else:
                self.__lst.append(self.__node(val))
                
        if _lst != None: self.__lst.extend(_lst)
    
    def __decode(self, v):
        if type(v) == unicode:
            return v
        elif type(v) == str:
            return v.decode(self.in_encoding)
        else:
            return unicode(v)
    
    def __node(self, val=u''):
        return [self.__decode(val), {}, {}]
    
    def __str__(self):
        return self.get_val().encode(self.out_encoding)
        
    def __unicode__(self):
        return self.get_val()
        
    def __repr__(self):
        return self.__lst.__repr__()
    
    def __len__(self):
        return len(self.__lst)
        
    def __cmp__(self, other):
        if isinstance(other, self.__class__):
            return cmp(id(self), id(other))
        else:
            return cmp(self.get_val(), unicode(other))
    
    def __iter__(self):
        return SimpleXML_Iterator(self.__lst)
    
    def __getitem__(self, key):
        if isinstance(key, basestring):
            if not self.__lst: self.__lst.append(self.__node())
            c = self.__lst[0][2]
            n = c.get(key)
            if n == None: n = c[key] = self.__class__()
            return n
        
        else:
            if type(key) != slice: key = slice(key, key + 1)
            end = key.stop
            k = len(self.__lst)
            while k < end:
                self.__lst.append(self.__node())
                k += 1
            return self.__class__(_lst=self.__lst[key])
        
    def __setitem__(self, key, val):
        n = self.__getitem__(key)
        if type(key) == slice:
            lst = n.__lst
            for i in xrange( len(lst) ): lst[i][0] = self.__decode(val[i])
        else:
            n.set_val(val)
        
    def __delitem__(self, key):
        if isinstance(key, basestring):
            if self.__lst: self.__lst[0][2].pop(key)
            
        else:
            if type(key) != slice: key = slice(key, key + 1)
            del self.__lst[key]
        
    def copy(self):
        cur_lst = self.__lst
        new = self.__class__()
        new_lst = new.__lst
        for l in cur_lst:
            children = {}
            for k, v in l[2].items(): children[k] = v.copy()
            new_lst.append([ l[0], l[1].copy(), children ])
        
        return new
    
    def __first(self):
        if not self.__lst: self.__lst.append(self.__node())
        return self.__lst[0]
    
    def get_val(self):
        if self.__lst:
            return self.__lst[0][0]
        else:
            return u''
    def set_val(self, v):
        self.__first()[0] = self.__decode(v)
    val = property(get_val, set_val)
    
    def attr(self, k, v=None, dv=None):
        attrs = self.get_attrs()
        if v == None:
            return attrs.get(k, dv)
        else:
            attrs[k] = self.__decode(v)
        
    def get_attrs(self):
        return self.__first()[1]
    def set_attrs(self, v):
        a = self.__first()[1]
        a.clear()
        for k, vv in v.items():
            a[k] = self.__decode(vv)
    attrs = property(get_attrs, set_attrs)

    def get_children(self):
        return self.__first()[2]
    def set_children(self, v):
        a = self.__first()[2]
        a.clear()
        a.update(v)
    children = property(get_children, set_children)

    def asxml(self, tag='root', top=True):
        s = u''
        for n in self.__lst:
            e = u''
            for k, v in n[2].items(): e += v.asxml(k, False)
            
            a = u''
            for k, v in n[1].items(): a += u' %s=%s' % (k, saxutils.quoteattr(self.__decode(v)))
            
            c = saxutils.escape(n[0])
            
            if e or c:
                s += u'<%s%s>%s%s</%s>' % (tag, a, c, e, tag)
            else:
                s += u'<%s%s/>' % (tag, a)
        
        if s and top: s = '<?xml version="1.0" encoding="' + self.out_encoding + '"?>' + s.encode(self.out_encoding)
        return s


class ConHandler(ContentHandler):
    def __init__(self, sx):
        ContentHandler.__init__(self)
        self.__sx = sx
        self.__sk = []
        self.root = None
        
    def startElement(self, name, attrs):
        if not self.__sk:
            self.root = name
            csx = self.__sx[len(self.__sx)]
        else:
            csx = self.__sk[-1][name]
            csx = csx[ len(csx) ]
            
        self.__sk.append(csx)
        csx.attrs.update(attrs.items())
        
    def endElement(self, name):
        self.__sk.pop()
    
    def characters(self, content):
        content = content.strip()
        if content: self.__sk[-1].val += content

def loads(s, root=[None]):
    sx = SimpleXML()
    ch = ConHandler(sx)
    parseString(s.strip(), ch)
    root[0] = ch.root
    return sx

def load(f, root=[None]):
    return loads(open(f, 'rb').read(), root)


if __name__ == '__main__':
    r = [None]
    p = load(r'e:\pk.txt', r)
    c = p.copy()
    
    p['tek'] = 123
    p[0:3] = ['12', 'ab', 'cd']
    del p[0]
    p['heading']['p'] = 'change'
    c['heading']['p'] = 'xxxxxx'
    
    print p.val
    
    print p.asxml()
    print c.asxml()
    
    #print p.asxml('root')


