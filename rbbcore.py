'''
Created on Sep 18, 2014

@author: rgabbot
'''

#import psycopg2
import urllib.parse
#import jaydebeapi
from collections import defaultdict

class Tagset(object):
    '''
    Python implementation of the RBB Tagset class
    '''
 
    __slots__ = ['tags']
 
    def __init__(self, tags=None):
        ''' 
        Construct a Tagset from another Tagset, a dict, or a single string.

        If 'tags' is a string:
        it is parsed as a String in the representation "name1=value1,name2,name3="
        where tags are delimited by ','
        If the tag contains one or more '=' characters, everything before the first '='
        is the name, and everything after it is the value.
        If the tag doesn't contain '=', the entire string is the name, and the value is null.
        Note: this version assumes the string argument is URL-encoded if necessary
        (e.g. if a name or value contains an equal sign - see encode/decode).
        So it is normally preferable to use the form below that takes 2 or more
        arguments which are interpreted as name/value pairs, and does not need decoding.
 
        '''
        self.tags = defaultdict(set)

        if tags is None or tags =="":
            pass # empty strings are valid, but split(",") returns an array with 1 element, not 0, so the normal-path code is incorrect.
        
        elif isinstance(tags, Tagset):
            self.tags = Tagset.fromString(str(tags)).tags
        
        elif isinstance(tags, str):
            self.tags = Tagset.fromString(tags).tags

        elif isinstance(tags, dict):
            { self.tags[k].add(v) for k,v in tags.items() }

#         for i in xrange(0, len(tags),2):
#             self.tags[tags[i]].add(tags[i+1])
        
#         if str is None or str =="":
#             return # empty strings are valid, but split(",") returns an array with 1 element, not 0, so the normal-path code is incorrect.
# 
#         for pair in str.split(","):
#             (name,value) = map(self.decode, pair.split("=", 1))
#             self.tags[name].add(value)

    '''
    '''
    @staticmethod
    def fromString(tags):
        t = Tagset()
        if tags is not None and tags != "":
            for pair in tags.split(","):
                if "=" in pair:
                    (name,value)=map(Tagset.decode, pair.split("=", 1))
                else:
                    (name,value) = (pair, None)
                
                if name == '':
                    raise ValueError("rbbcore.Tagset.fromString error: the empty string is not a valid tag name, found in tagset: \""+tags+"\"")
            
                t.add(name, value)
        return t

    def add(self, name, value):
        self.tags[name].add(value)

    @staticmethod
    def makeTagset(t):
        return t if isinstance(t, Tagset) else Tagset(t)

    def addTags(self, tags):
        tags = self.makeTagset(tags)
        for name in tags.tags:
            for value in tags.tags[name]:
                self.add(name, value)

    def setTags(self, newTags):
        ''' 
            remove any/all pairs with names in newTags, then add newTags
            Does not remove any existing names not overwritten by newTags. 
        '''
        newTags = self.makeTagset(newTags)

        for name in newTags.tags:
            self.remove(name)

        self.addTags(newTags)

    def setTag(self, name, value):
        '''
            set a single name/value pair, first removing any/all existing tags with the specified name.
        '''

        self.remove(name)
        self.add(name, value)

    def remove(self, name):
        ''' remove any/all name/value pairs with the specified name '''
        if name  in self.tags:
            del self.tags[name]

    def getValue(self, name):
        if name in self.tags:
            return next(iter(self.tags[name]))
        else:
            return None

    def __eq__(self, other):
        return (isinstance(other, self.__class__)
            and self.tags == other.tags)

    def __ne__(self, other):
        return not self.__eq__(other)

    @staticmethod
    def decode(s):
        return urllib.parse.unquote(s)

    @staticmethod
    def encode(s):
        '''
        URL-encode the given string if it contains any rbb punctuation characters.
        The source of the list of punctuation characters and further documentation are found in Tagset.java
        '''
        if any(c in "%=,\t\n :;+" for c in s):
            return urllib.parse.quote(s)
        else:
            return s

    def __str__(self):
        pairs = []
        for name in sorted(self.tags):
            if None in self.tags[name]:
                raise Exception("uh oh")
            for value in sorted(self.tags[name]):
                pair = self.encode(name)
                if(value is not None):
                    pair += "="+self.encode(str(value))
                pairs.append(pair)
        return",".join(pairs)

    def __repr__(self):
        return self.__str__()

    def isSubsetOf(self, superSet, treatEmptyAsNull = False):
        if superSet is None:
            return False
        
        for subsetName in self.tags:
            superSetValues = superSet.tags[subsetName]
            if superSetValues is None:
                return False # this has a name that the would-be superset does not.

            for subsetValue in self.tags[subsetName]:
                if subsetValue is None or (treatEmptyAsNull and subsetValue == ""):
                    continue # if a subset tag has a null value it matches any tag in the superset with the same name.
                if not subsetValue in superSetValues:
                    return False

        # we didn'superSet find anything we had that superSet did not, so we're a subset of superSet.
        return True


    @staticmethod
    def toTagsets(obj):
        '''
        Creates an list of Tagsets from:
        * A string containing 0 or more tagsets separated with semicolon, e.g.: "" or "a=b" or "a=b;c=d"
            note: the empty string "" returns a 0-element array, rather than a 1-element array containing an empty Tagset.
        * A Tagset instance or list of Tagset instances
        * Something that iterates over elements that are Tagset instances, or convert to strings that can be parsed as Tagsets
        
        Any Tagset instances included in the input are only shallow-copied, not deep copied.
        '''
        if isinstance(obj, Tagset):
            return [obj]

        if isinstance(obj, str):
            if "" == obj:
                return []
            return [Tagset(t) for t in str(obj).split(";")]

        lst = []
        for t in obj:
            if isinstance(t, Tagset):
                lst.append(t)
            else:
                lst.append(str(t))
        return lst

class Event(object):
    '''
    Python implementation of the RBB Event class
    '''

    __slots__ = ['message_id', 'start', 'end', 'tags']

    def __init__(self, id, start, end, tags):
        '''
        '''
        self.message_id = id
        self.start = float(start)
        self.end = float(end)
        self.tags = Tagset(tags)

    def __str__(self):
        '''
        Outputs the string representation of an RBB Event that is also valid as input for rbb.put(), so it should not be changed arbitrarily.
        '''
        return "start={},end={},{}".format(Tagset.encode(str(self.start)), Tagset.encode(str(self.end)), self.tags)
        
    def __repr__(self):
        return self.__str__()

class RBBFilter(object):
    ''''
    RBBFilter specifies a setTags of Events on the basis of tags, time, ID, 
    attached data (e.g. timeseries data), etc.

    The basic problem addressed by this class is that RBB Events have
    several attributes (start/end time, tags, ID) any of which may
    be used to select events for processing.  So methods that require sets
    of events get very clunky when using positional parameters for every possible
    criteria.

    An RBBFilter has a string representation.  A tagset string is also an
    RBBFilter string.
    '''

    def __init__(self, IDs=None, attachmentInSchema=None, start=None, end=None, timeCoordinate=None, tags=None, ifExists=None, exactTags=None):
        if IDs is not None:
            self.IDs = [int(ID) for ID in IDs]
            
        if attachmentInSchema is not None:
            self.attachmentInSchema = attachmentInSchema
            
        if start is not None:
            self.start = start
            
        if end is not None:
            self.end = end
            
        if timeCoordinate is not None:
            self.timeCoordinate = timeCoordinate
            
        if tags is not None:
            self.tags = Tagset.toTagsets(tags)
            
        if ifExists is not None:
            if self.ifExists is None:
                self.ifExists = [ifExists]
            else:
                self.ifExists.append(ifExists)
            
        if exactTags is not None:
            exactTags = bool(exactTags) 

    def __str__(self):
        '''
        Convert this object to a one-line string representation.
        Note: this is used programmatically within the code, so it must
        match fromString and not be changed willy-nilly.
        However it is also meant to be human-readable.
        '''
    
        lst = []
    
        if hasattr(self, 'IDs'):
            lst.append("IDs:"+",".join(self.IDs))
    
        if hasattr(self, 'attachmentInSchema'):
            lst.append("Schema:"+self.attachmentInSchema);
    
        if hasattr(self, 'start'):
            lst.append("Start:"+str(self.start))
    
        if hasattr(self, 'end'):
            lst.append("End:"+str(self.end))
    
        if hasattr(self, 'timeCoordinate'):
            lst.append("timeCoordinate:"+str(self.timeCoordinate))
    
        if hasattr(self, 'tags'):
            lst.extend([str(t) for t in self.tags])
    
        if hasattr(self, 'ifExists'):
            lst.extend(["ifExists:"+ex for ex in self.ifExists])
    
        if hasattr(self, 'exactTags'):
            lst.append("exactTags:"+str(self.exactTags).lower())
    
        return ";".join(lst)

class RBB(object):
    '''
    '''
    
    def connect(self, jdbc):
        # psycopg2 default port is 5432, whereas default h2 pg server port is 5435

#         self.conn = jaydebeapi.connect("org.h2.Driver", jdbc, ["sa", "x"])
#        conn = jaydebeapi.connect("org.h2.Driver", url, ["sa", "x"], "/Users/angelo/websites/GEPR/h2/bin/h2-1.4.197.jar",)
        
#        self.conn = psycopg2.connect(database=str(dbName)+";ifexists=true", user="sa", password="x", host="localhost", port=5435)
#         --drop alias if exists RBB_FIND_EVENTS;
#         --CREATE ALIAS IF NOT EXISTS RBB_FIND_EVENTS for "gov.sandia.rbb.impl.h2.statics.H2SEvent.findSql";
        pass

    def find_events(self, rbbfilter):
        cursor = self.conn.cursor()
        print("finding "+str(rbbfilter))
#        cursor.execute("call RBB_FIND_EVENTS(%s)", (str(rbbfilter),))
#        cursor.execute("select RBB_FIND_EVENTS(%s) from dual", (str(rbbfilter),))
#        cursor.execute("select RBB_FIND_EVENTS('{}') from dual".format(rbbfilter))
        cursor.execute("call RBB_FIND_EVENTS('{}')".format(rbbfilter))
        return [Event(row[0], row[1], row[2], row[3]) for row in cursor.fetchall()]

    def find_event_tagsets(self, rbbfilter):
        ''' find all combinations of the tag values subjectID,type found in Events in the RBB '''
        cursor = self.conn.cursor()
        cursor.execute("call RBB_EVENT_TAG_COMBINATIONS(%s)", (str(rbbfilter),))
        return [(Tagset(row[0]), row[1]) for row in cursor]
    
    def get_event_index(self, tag_names, op = lambda x : x, events=None):
        if events==None:
            t = Tagset()
            for tag_name in tag_names:
                t.add(tag_name, None)
            events=self.find_events(t)
            
        result = {}
        last_tag = tag_names.pop()
        for ev in events:
            dict0 = result
            for tag_name in tag_names:
                tag_value = ev.tags.getValue(tag_name)
                if tag_value not in dict0:
                    dict0[tag_value] = {}
                dict0 = dict0[tag_value]
            tag_value = ev.tags.getValue(last_tag)
            dict0[tag_value] = op(ev)
        return result

    def get_tag_value_index(self, index_tags, tag_name, events=None):
        if events == None:
            t = Tagset({key : None for key in index_tags})
            t.add(tag_name, None)
            events = self.find_events(t)
        return self.get_event_index(index_tags, op=lambda ev : ev.tags.getValue(tag_name), events=events)
    
