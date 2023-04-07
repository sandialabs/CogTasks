'''
the messaging module facilitates sending/receiving messages, including using the messages to control work flow, 
using several means to queue and order the messages.  When a recipient requests a message, the following criteria apply:

    1) The current state of the Message is SUBMITTED
    2) the recipient specifies a Filter (as with simpy FilterStore).  Only messages for which the filter returns true may be returned.
    3) A message can have a list of other messages that must be done first, called 'preconditions'.  A message won't be offered until all its preconditions are CLOSED
    4) Each message has a priority.  A message will not be offered until after any other lower-priority messages that meet the above criteria
    5) Among messages tied by the above criteria, messages are ordered by msg_id, i.e. by creation time (fifo order)

@author: rgabbot
'''
from simpy.resources.store import Store, StorePut, StoreGet, FilterStoreGet
from simpy.core import BoundClass
import simpy
from enum import Enum
import bisect
from builtins import isinstance
import sys
from collections import defaultdict, Iterable
from simpy.events import AnyOf

class State(Enum):
    CREATED="CREATED" # initial state - not submitted yet.
    SUBMITTED="SUBMITTED"
    ACCEPTED="ACCEPTED"
    CLOSED="CLOSED"

class Message(simpy.Event):
    ''' 
    A set of name=value fields.
    Access a field by referencing it, e.g. messagename.fieldname

    Each Message is assigned a unique ID integer.  IDs are assigned in increasing order by time of creation.
      (note: Message IDs are unique across MessageBroker instances, so within a given MessageBroker instance,
      msg_id's don't necessarily start at 1 and aren't necessarily successive values)
    '''
    
    next_msg_id=1 # each Task is auto-assigned a sequence number, which is used for fifo ordering among Tasks with equal priority
    
    def __init__(self, env, priority=0, specified_msg_id=None, **kwargs):
        '''
        specified_msg_id: this should normally not be specified, it is only specified for special purposes e.g. serialization.
        
        kwargs allows the creator of the job to set whatever attributes will trigger the filtering desired.
        to see which attributes to set to activate filters, see the documentation for the filters below,
        or test_messaging.py for examples.
        
        If you don't like the kwargs approach, make a subclass in which __init__ takes specific parameters and calls super().__init__ with them.
        
        'priority' will be converted to a float
        '''
        super(Message, self).__init__(env)
        if specified_msg_id == None:
            self._msg_id = Message.next_msg_id
            Message.next_msg_id+=1
        else:
            self._msg_id = int(specified_msg_id)
        self._msg_priority = float(priority) # it's important to store this as a number or else comparing priorities will not work as expected, e.g. "-3" < "-4" (as strings compared lexicographically, character-by-character)
        self._msg_state = State.CREATED
        self._msg_time_submitted = None # will be set to record when the Task was put into MessageBroker
        self._msg_time_accepted = None # will be set to record when they started doing it
        self._msg_time_closed = None # will be set to record when the finished.

        self.__dict__.update(kwargs)
        self._kwargs = kwargs # keep track of which attributes were added-on

#         print("GOT KWARGS: {}".format(", ".join(["{}={}".format(k,v) for k,v in kwargs.items()])))

    def add_feature(self, name, value):
        '''
        Add a name/value feature.
        '''
        if name.startswith("_msg_"):
            raise ValueError("features added to Message cannot be prefixed with _msg_ but got: \"{}\"".format(name))
        self._kwargs[name]=value
        setattr(self, name, value)

    def add_features(self, names_values):
        '''
        Add a name/value features from a dict.
        '''
        for k,v in names_values.items():
            self.add_feature(k,v)
    
    def __str__(self):
        return "Message: {}".format(" ".join(["{}={}".format(a,b) for a,b in self.getLogAttributes()]))

    def __lt__(self, other):
        '''
        Messages are compared by ID, not anything else e.g. priority.
        The code relies on this to efficiently retrieve a message by ID, which is used to efficiently check dependencies.
        '''
        return self._msg_id < other._msg_id

    def getLogAttributes(self):
        '''
        Get the attributes for this task that should be added to the logfile.
        If 'None' then the task will not be logged.
        These attributes will not necessarily be displayed to the user, but determine what processing can be done on the log entries later.
        '''
        return [("taskID", self._msg_id), ("timeSubmitted", self._msg_time_submitted), ("start", self._msg_time_accepted), ("end", self._msg_time_closed), ("taskPriority", self._msg_priority), ("taskState", self._msg_state.value)] + [(a, getattr(self, a)) for a in self._kwargs.keys()]

    def succeed(self, value=True, message_fields={}):
        ''' override of simpy.Event.succeed '''
        #print("message.succeed: {}".format(id(self)))
        assert self._msg_state == State.ACCEPTED
        self._msg_state = State.CLOSED
        self._msg_time_closed = self.env.now
        self.add_features(message_fields)
        super().succeed(value)

    def fail(self, exception, message_fields={}):
        ''' override of simpy.Event.fail '''
        #print("message.fail: {}".format(id(self)))
        assert self._msg_state == State.ACCEPTED
        self._msg_state = State.CLOSED
        self._msg_time_closed = self.env.now
        self.add_features(message_fields)
        super().fail(exception)

    def defer(self, message_fields={}):
        '''
        Revert the message from ACCEPTED back to SUBMITTED,
        optionally adding/changing message fields.
        '''
        assert self._msg_state == State.ACCEPTED
        self._msg_state = State.SUBMITTED
        self.add_features(message_fields)

    def matches(self, **fields):
        '''
        returns true if this message has all the name=value pairs specified.
        '''
        return all(item in self.__dict__.items() for item in fields.items())

class MessageFilter:
    '''
    The purpose of message filters is to restrict the delivery of a message to potential recipients.
    This is a base class which by default allows all messages.
    
    The application can use any of the filters below as the 'filter' parameter for Message_Broker.get
    '''
    
    def __call__(self, msg):
        ''' the default filter passess everything '''
        return True

'''
To help diagnose why some messages are not received, we track all the addresses of receivers and
messages.  Any address used on a message but not by a receiver cannot be received.
'''
message_address = set()
receiver_address = set()

class AddressFilter(MessageFilter):
    '''
    
    If the message has an 'address' string attribute, the message will only be delivered to a recipient with that address.
    The recipient address is specified in the constructor of this filter.
    
    If the message has no 'address' attribute, or it is None, no messages are filtered out (can be delivered to anybody)
    
    Either the address of the message or the recipient can be specified as iterables (i.e. array, list, set...)
    Then the filter matches if the intersection is not empty - i.e. any of the message addresses match any of the recipient addresses.
    This allows a message to be sent to any of several parties, and allows a recipient to have several names or belong to several groups, e.g. ['joe_smith', 'welders', 'diabetics'].
    
    Note that this does not mean a message will be delivered to multiple recipients or to the same recipient multiple times - only that 
    only that this particular filter would pass for anybody with a matching address.
    
    Message attributes:
    address: if present, a string or iterable of strings specifying acceptable recipient addresses
    
    AddressFilter __init__parameters:
    address: a string specifying the address of the recipient, or iterable specifying this recipient's multiple addresses   
    '''
    
    def __init__(self, address):
        self.address = self._make_address_set(address)
        ''' 
        store self.address as a set even if it only contains one element to simplify the __call__ function
        address can be specified as None, in which case only messages not addressed to anybody can be received.
        '''

    @staticmethod        
    def _make_address_set(name):
        if name is None:
            return None
        if isinstance(name, str):
            return set([name])
        return set(name)

    def __call__(self, msg):
        m = None # this will be the address specified in the message
        try:
            m = msg.address
        except AttributeError:
            pass # if missing, leave a as None
        
        if m is None:
            return True # is not addressed to anybody in particular
        
        if self.address is None:
            return False # message is addressed to somebody, but this potential recipient doesn't specify an address

        receiver_address.update(self.address)

        if isinstance(m, str):
            message_address.add(m)
            return m in self.address
        
        # if the message address isn't a string, treat it as an iterable of addresses.
        for m0 in m: # m is required to be iterable but may not be a set, so this code just iterates it instead of taking the intersection of it and self.address.
            message_address.add(m0)
            if m0 in self.address: # self.address is a set so this is reasonably efficient.
                return True
             
        return False

class MessageBrokerFilter(MessageFilter):
    '''
    MessageBrokerFilter is just a MessageFilter that is instantiated automatically in the message broker.
    These are instantiated in MessageBroker.__init__, not for each 'get' request, so they don't have
    any information about the recipient, only the message.
    
    A MessageBrokerFilter is activated by populating the message with the required attribute(s)
    '''
    pass


class PreconditionsFilter(MessageBrokerFilter):
    '''
    Message must not be delivered until a list of other messages are CLOSED
    
    Message attributes:
    preconditions: if present, it is an iterable of other messages that must all be CLOSED before this message will sent.
    '''
    def __call__(self, msg):
        
        try:
            preconditions = msg.preconditions
        except AttributeError:
            return True # if msg has no preconditions, it passes.   (If p.state is missing, something is very wrong)

        return all(p._msg_state == State.CLOSED for p in preconditions)

class FilterSubmitted(MessageBrokerFilter):
    '''
    Only try to deliver messages that are in the SUBMITTED state, i.e. exclude messages already ACCEPTED, CLOSED, etc.
    This filter is mandatory since otherwise the same message will be delivered in an infinite loop
    
    Message attributes:
    state (this is created by Message.__init__ and managed by the message broker, do not reassign it) 
    '''
    def __call__(self, msg):
        return msg._msg_state == State.SUBMITTED 

class MessageBroker(Store):
    """
    A SimPy Resource (patterned after simpy.resources.store.FilterStore) with unlimited slots for storing Messages
    with the following properties to determine which is selected next:

    Message Broker retains all the messages ever submitted to it, for logging / reporting / analysis purposes.
    Internally, he messages are ordered by message ID, so that a message can be retrieved by its msg_id efficiently. 

    It is allowable to change anything about a message even after submitting it to MessageBroker at any time, EXCEPT
    its msg_id.  (This hampers optimizing retrieval but supports the function of reflecting the current status
    of a message as it changes over time)
    """

    def __init__(self, env):
        super(MessageBroker, self).__init__(env)
        self.env = env
        self.filters = [FilterSubmitted(), PreconditionsFilter()]

    put = BoundClass(StorePut)
    '''
    This acts as a method that (indirectly) calls _do_put to submit the message.  
    (This design comes from SimPy store)
    
    If the job state is CREATED (i.e. it hasn't been 'put' into a broker before), 
    the state of the message will be set to State.SUBMITTED and time_submitted will be updated.
    
    A previously-assigned message (i.e. returned by 'get') can be 'put' again, 
    which will not duplicate it, and will not automatically set the state.
    '''
    get = BoundClass(FilterStoreGet)
    """
    Request a to get an *item*, for which *filter* returns ``True``, out of the store.
    If no filter argument is supplied to get(filter), or the specified filter is None i.e. get(None), then the caller will accept any message,
    but the message broker's filters still apply (i.e. the caller may not be offered some messages because e.g. they are for somebody else)
    """

    def _do_put(self, put_event):
        '''
        See 'put' for documentation
        '''
        # print("MessageBroker._do_put {}".format(put_event.item))
        
        assert(isinstance(put_event.item, Message))
        message = put_event.item
        
        message._msg_state = State.SUBMITTED # this is already the case the first time a message is 'put' into MessageBroker, but a message can be resubmitted.
        message._msg_time_submitted = self.env.now
        
        if self._get_message_index(message._msg_id) is None:        
            # use bisect_left to determine the insertion point.
            # this will always simply be the end of the list (ie. self.items.append) if the messages are 'put' in the order they were created,
            # so this is just in case the caller puts them in out of order.
            i = bisect.bisect_left(self.items, message)
            # print("inserting at {} in list of length {}".format(i, len(self.items)))
            self.items.insert(i, message)
        
        put_event.succeed()

    def _apply_filters(self, event, message):
        '''
            generator to apply each filter, in order.
            by calling this from all(), any filters after the first failure are not called.
        '''
        for f in self.filters:
            yield f(message)
        if event.filter is not None:
            yield event.filter(message)

    def _do_get(self, event):
        message = None
        for m in [m0 for m0 in self.items if m0._msg_state == State.SUBMITTED]: # inlining the SUBMITTED filter
            if not all(self._apply_filters(event, m)): # must pass all filters
                continue
            if message is not None:
                if message._msg_priority < m._msg_priority: # among messages that are acceptable (i.e. pass all filters) disregard any with higher than minimal priority
                    continue
                if m._msg_priority < message._msg_priority:
                    message = None
            if message is None or m._msg_id < message._msg_id: # this imposes fifo ordering among all messages that are eligible to be returned.
                message = m
                    
        if message is not None:
            assert message._msg_state == State.SUBMITTED
            # the message is not removed from the MessageBroker instance; instead it is marked as assigned so it won't be dispatched again.
            message._msg_state = State.ACCEPTED
            message._msg_time_accepted = self.env.now
            event.succeed(message)
            # print("MessageBroker._do_get {}".format(message))
            
        return True

    def get_items(self, filter=None):
        for m in self.items:
            if filter is None or filter(m):
                yield m

    def get_grouped_items(self, key=lambda m: m._msg_id, filter=None):
        '''
        returns a dict each entry mapping a key to a list of messages for which the key function returned that value.
        '''
        d = defaultdict(list)
        for m in self.items:
            if filter is None or filter(m):
                d[key(m)].append(m)
        return d

    def get_message_by_id(self, msg_id):
        ''' Efficiently retrieve the Message instance by ID, or raise ValueError if msg_id is invalid '''
        i = self._get_message_index(msg_id)
        if i is None:
            raise ValueError("MessageBroker.get_message_by_id: invalid msg_id {}".format(msg_id))
        return self.items[i]

    # def find_message_by_key(self, attr_name, attr_value):
    #     ''' perform a linear search for the single message whose specified attribute has the specified value.
    #     Raises ValueError if none match or more than 1 match. '''
    #     results = [i for i in self.items if hasattr(i,attr_name) and getattr(i,attr_name)==attr_value]
    #     if len(results) != 1:
    #         print("find_message_by_key {}={} found {} results, should be 1".format(attr_name, attr_value, len(results)), file=sys.stderr)
    #         raise ValueError
    #     return results[0]

    def find_messages(self, **fields):
        return [msg for msg in self.items if msg.matches(**fields)]

    def _get_message_index(self, msg_id):
        ''' Retrieve the integer index of the specified message from self.items, or None if invalid. '''
        i = bisect.bisect_left(self.items, Message(self._env, specified_msg_id=msg_id))
        if i != len(self.items) and self.items[i]._msg_id == int(msg_id):
            return i
        else:
            return None
        

    def __str__(self):
        return "\n".join(["-"*12, "Messages:"]+[str(j) for j in self.items]+["-"*12])  # should this use os.linesep instead of "\n" ?
    
    def count_messages(self, state = None):
        '''
            Count how many messages match the specified criteria.
            Unspecified critera (with values None) are not applied.
            This consumes time linear to the total number of messages, so avoid calling it repeatedly if not necessary.
        '''
        n = 0
        for j in self.items:
            if state is not None and j._msg_state != state:
                continue
            n += 1
            
        return n

    def add_preconditions(self, msg, preconditions):
        '''
        Add preconditions to msg - it will not be assigned until all preconditions are closed.  (see PreconditionsFilter)
        msg: the message to which the precondition will be added - a message instance or ID
        preconditions: an instance or iterable of message instances or IDs
        '''
        
        if not isinstance(msg, Message):
            msg = self.get_message_by_id(msg)
            
        if isinstance(preconditions, str): # id as string, e.g. "23" -> 23
            preconditions = int(preconditions)
        
        if isinstance(preconditions, Iterable):
            for p in preconditions:
                self.add_preconditions(msg, p)
            return

        p = preconditions
        if not isinstance(p, Message):
            p = self.get_message_by_id(p)
            
        # now make sure msg has a preconditions attribute of type set
        if not hasattr(msg, "preconditions"):
            msg.preconditions = set()
        elif not isinstance(msg.preconditions, set):
            msg.preconditions = set(msg.preconditions) # convert to set.
            
        msg.preconditions.add(p)

    def report_no_such_address(self):
        '''
        print out a list of addresses to which messages were addressed, but did not belong to any recipient
        '''

        print("WARNING: messages were sent to these addresses, which did not belong to any reciever:",
              ", ".join(message_address.difference(receiver_address)))

    def send_sync(self, msg, timeout=None):
        '''
        synchronous send: put the name/value pairs into a message and send it through the message broker, and wait for the response for up to the specified amount of time.

        If the timeout is exceeded, the sender receives an exception.  Note however that the recipient is not notified or interrupted.

        The recipent must close the message with msg.succeed(True) on success, or msg.succeed("<error message string>") to raise an exception from send_sync to the caller.
        Additional information is communicated back by adding fields to be altered to the call to 'succeed'
        msg.fail(exception) in contrast will result in an exception from environment.run() 
        disrupting the sim so it should not be used except for unexpected / unrecoverable exceptions.
        
        Possible results:
        1) everything finished as expected.  Returns the message after modification by the recipient.
        2) the timeout was exceeded before the message was marked completed. Raises an exception including string "timed out"
        3) If the recipient closes the message with msg.succeed("<error string...>") then an exception will be raised by this function with that string.
        
        Timeout Note: in simpy, setting a Timeout will schedule an event for that time.  What this means is that if you use an extremely
        large timeout, and then call env.run(), it will advance simulation time until at least that time.

        '''
        self.put(msg)

        outcomes = [msg]

        if timeout:
            outcomes += [self.env.timeout(timeout, value="Timeout")]

        results = yield AnyOf(self.env, outcomes)

        # the simpy documentation says:
        # "The value dict of AnyOf will have at least one entry." and
        # "the event instances are used as keys and the event values will be the values."
        # so, the msg object will be in results if it fired, and in this case if it also timed out simultaneously, ignore that.

        if msg in results:
            if results[msg] is True: # case 1) finished as expected
                return msg
            else: # case 3) error string returned
                raise Exception("send_sync: recipient encountered error handling {}: {}".format(msg, results[msg]))
        else: # case 2) timeout exceeded before run returned.
            raise Exception("send_sync: timed out after {} seconds sending {}".format(timeout, msg))

