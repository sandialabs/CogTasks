
import sys
from cogtasks.rbbcore import Tagset

class RBBLogger:
    
    defaultLogFile = None
    
    def __init__(self, tags, file=None):
        '''
        If file=None, a new file, default.rbb, will be created (overwriting any previous contents) and shared with
        any other RBBLogger instances in this process for which no file is specified.  note this will not work
        correctly if multiple processes use this default concurrently since each will overwrite the others.

        If file is a string, a new file by this name will be used by this RBBLogger instance, overwriting a
        previous file by this name if one existed (even if created by another RBBLogger instance in this same process)

        Otherwise, file must be an already-open file, in which case it can be shared with other RBBLogger instances
        in this process
        '''
        if file is None:
            if RBBLogger.defaultLogFile is None:
                filename = "default.rbb"
                print("Writing to {}".format(filename), file=sys.stderr)
                RBBLogger.defaultLogFile = open(filename, "w")
            self.rbbLog = RBBLogger.defaultLogFile
        elif isinstance(file, str):
            self.rbbLog = open(file, "w")
            print("Writing to {}".format(file), file=sys.stderr)
        else:
            self.rbbLog = file
        
        self.times = {} # this is the previous time at which each entity was reported.
        self.tags = tags
        if self.tags is None:
            self.tags=""
        if self.tags != "":
            self.tags = Tagset(tags)

        self.hosts = None

    def log(self, tags, time, end_time=None):
        '''
            Enter the specified tags (name/value pairs) into the log 
            tags is a list of tuples [(name,value),(name2,value2)...]
            to which will be added any tags specified at construction.
        '''
        t = Tagset(self.tags)
        if end_time is None:
            t.add("time", time)
        else:
            t.add("start", time)
            t.add("end", end_time)
        
        for a, b in tags:
            t.add(a, b)
            
        print("{} {}".format(self.tags,  t), file=self.rbbLog, flush=True)
        

    def logAttrs(self, time, entity, attrs, end_time=None):
        '''
            Log values for discrete attributes of an entity (i.e. RBB tag)
            attrs is a list of attributes to record.
            If an attribute is specified as a string, then getattr(entity, attribute) is used to obtain its value creating an (attribute, value) tuple for the log.
            Otherwise the attribute must be a tuple and (attr[0],attr[1]) are logged.  In other words the tuple is logged as given.
        '''

        def get(a):
            if isinstance(a, str):
                return (a, getattr(entity, a))
            else:
                return (a[0], a[1])

        attrs = [get(a) for a in attrs]
        
        attrs += [("entityType", type(entity).__name__), ("name", entity.name)]

        self.log(attrs, time, end_time)        
        
    def logEntityCreated(self, time, entity):
        '''
        start a timeseries of positions to be logged for the specified entity using logEntityPos and ended with logEntityDestroyed
        '''
        tags = Tagset(self.tags)
        tags.add("start", time)
        tags.add("entityType", type(entity).__name__)
        tags.add("variable", "position")
        tags.add("name", entity.name)
        tags.add("color", entity.color)
        
        print("{} {}".format(self.entityTag(entity), tags), file=self.rbbLog)
 
    def logEntityPos(self, time, entity):
        if entity in self.times and self.times[entity] >= time:
            return # we already made a report at or after the specified time
        
        p = entity.getPosition(time)
        if p is None:
            print("{} Not logging null position for {}".format(time, self.entityTag(entity)))
            return

        print("{} {},{},{}".format(self.entityTag(entity), time, p[0], p[1]), file=self.rbbLog)

        self.times[entity] = time

    def logEntityDestroyed(self, time, entity):
        print("{} {}".format(self.entityTag(entity), time), file=self.rbbLog)

    def entityTag(self, entity):
        t = Tagset(self.tags)
        t.setTag("entity", entity.name)
        return str(t)
