'''
Created on Apr 16, 2020

@author: rgabbot
'''


from cogtasks.actr_person import actr_eval, ActrTask, ActrPerson, check_actr_tasks
from enum import Enum
from cogtasks.messaging import Message, AddressFilter

class Opcode(Enum):
    '''
    These opcodes are reserved values that relate to Messages (in the Message Broker construct) sent/received by an actr.
    
    These constitute a protocol between the two components of a single "person" - the act-r part (in lisp) and the python part (in ActrMessagingPerson, below).
    ActrMessagingPerson then makes calls directly in python to other parts of the software, so these Opcodes should usually not need to appear except in this file,
    or ActrTask code that writes lisp code that uses these strings.
     
    The actr receives information by having it displayed on its 'visicon', which shows a set of features which are name/value pairs.

    The actr sends information by speaking a string, which is identified by its prefix.
      This means that no opcode should be a prefix of any other
      the expected format of the rest of the string depends on the prefix.
      Spoken strings representing Message Broker Messages consist of name/value pairs, i.e. they are to be split on whitespace and should contain an even number of fields.
      the reason for this is because a Message is a set of name/value pairs, as are visicon features, and actrs speak primarily to communicate Messages to each other. 
    
    '''
    
    REQUEST = "messagebroker request_msg" 
    ''' this is what an actr says to request that the message broker send (assign) the next available Message to them.'''
    
    CLOSE = "messagebroker close_msg" 
    ''' This is what an actr says to mark the message they were previously sent as 'closed', so any messages that depended on it are eligible to be assigned.
        The rest of the string (if any) consists of name/value pairs which will be set in the message (as return values) before it is closed.
    '''
    
    DEFER = "messagebroker defer_to_msg" 
    ''' 
        This is what an actr says to defer the message they were working on until after another message is closed.
        Following this string is the ID of the message to defer to.
    '''
    
    SEND = "messagebroker send_msg" 
    ''' 
        this is what an actr says to create a new message for the message broker to send out.  
        The rest of the string consists of name/value pairs constituting the content of the Message
        Some names (such as "address") have special meaning to the MessageBroker
    '''
    
    CONFIRM_SEND = "messagebroker confirm_msg message_id =message_id" 
    '''
        These are the visicon features (two name/value pairs) the message broker shows on the actr's screen 
          to confirm that the message they sent has been queued.  =message_id is replaced by the id of the new message.
        Likewise, the actr watches for these features to appear in its visicon to receive this information.
    '''

    REQUEST_REPLY = "messagebroker request_reply_msg" 
    ''' 
        This is what an actr says to create a synchronous request.
        It is like a SEND except the sender will await the REPLY   
        Like a send, the rest of the string consists of name/value pairs constituting the content of the Message
        Some names (such as "address") have special meaning to the MessageBroker
    '''
    
    REPLY = "messagebroker reply_msg message_id =message_id"
    '''
        These are visicon features (name/value pairs) shown on on the actr's screen in response to a REQUEST 
        In the reply,  =message_id is replaced by the id of the new message.
        Likewise, the actr watches for these features to appear in its visicon to receive this information.
        In addition all the name/value pairs from the message (at the time it was closed) will be put into the visicon. 
    '''

    MESSAGE_FIELD_REQUEST = "messagebroker message_field_request"
    '''
        This is what an actr says to retrieve one field of the specified message from the message broker.
    '''
    
    MESSAGE_FIELD_REPLY = "messagebroker message_field_reply message_id =message_id message_field =message_field message_field_value =message_field_value"
    '''
        These are the visicon features (name/value pairs) shown on the actr's screen in response to MESSAGE_FIELD_REQUEST
        In the reply, 
        =message_id is replaced by the id of the message specified in the MESSAGE_FIELD_REQUEST
        =message_field is replaced by the name of the field requested
        =message_field_value is replaced by the value of the specified field.  (i.e. this is the return value)
    '''
    
    MESSAGE_ADD_PRECONDITION = "messagebroker message_add_precondition "
    '''
        This is what an actr says to add a precondition to a message.
        See Message.
    '''
    
    COMMENT_PREFIX = "Comment: " 
    ''' 
    an actor can say this followed by whatever they want, it will be ignored by handle_actr_speech processing, and just printed out.
    '''

    ASSIGN_TASK = "assign_task"
    '''
        This is a message field that must be present in a message that will assign an actr to perform a task. 

        Note, this means for one actr to task another through a Message, they must speak a string containing both 
        SEND (to get the message sent) and ASSIGN_TASK (to assign the task).
    '''
    
    RECEIVE_TASK_ASSIGNMENT = ASSIGN_TASK + " =taskname message_id =message_id"
    '''
        These are the visicon features shown on the actr's screen to indicate they
          have received a Message which is an assignment to perform 'taskname'.
          In the visicon features =taskname will be replaced by the name of the task,
          and =message_id will contain the ID of the message.
          In ActrMessageTask, this must correspond to a Task as documented in ACTR Subtasks.docx,
          the actr code for which can be generated  using ActrTask/ActrMessageTask.
        
    '''

    WAITING_FOR_MESSAGE = "waiting-for-message"
    '''
         This is the name of the task-state in which the actr sits while they are waiting to receive a message.
         ALL the various message handlers that might be defined wait in this same task-state, so
         they must either differ in what they expect to see on the screen, or else the actr conflict resolution mechanism will come into play. 
    '''


def set_task(message, taskname):
    '''
        Modify the message by adding the name/value pair which the actr will recognize as a task assignment.
    '''
    message.add_feature(Opcode.ASSIGN_TASK.value, taskname)
    return message

def string_to_dict(s):
    '''
    convert a list alternating names and values into a dict: "k1 v1 k2 v2" -> {"k1":"v1", "k2":"v2"}
    This comes up because it is done in actr code, e.g assigning slot buffers.
    '''
    l=s.split()
    return dict(zip(l[::2], l[1::2]))

class ActrMessageTask(ActrTask):
    '''
    This is an extension of ActrTask with additional productions related to messaging.
    '''
    
    def __init__(self, task_name, main_task=False, inputs=None, outputs=[]):
        super().__init__(task_name, main_task=main_task, inputs=inputs, outputs=outputs)
    
    def p_send_task_assignment(self, task_name, from_state=None, to_state=None, conditions=None, param_slots=[], address=None, message_fields={}, description=None, cleanup=None):
        '''
        Send a message that is an assignment to perform the specified task.
        task_name: is manditory.
        address: specifies who will receive the assignment.  (This defaults to None but it should be specified or else the sender may receive the request)
        param_slots: a list of slots in the goal buffer that will be added as name/value pairs in the message.
          Any param_slots not specified as outputs of this Task (to init) will be added to the list of slots to cleanup when the task finishes.
        message_fields: a dict of arbitrary name/value pairs that will be added as pairs in the message.
        
        message_id <id> will be stored in a goal slot upon return.
        '''
        assert task_name is not None
        assert task_name != ""
        message_fields = message_fields.copy()
        message_fields[Opcode.ASSIGN_TASK.value] = task_name

        self._p_send_message(Opcode.SEND, from_state=from_state, to_state=to_state, conditions=conditions, param_slots=param_slots, address=address, message_fields=message_fields, description=description, cleanup=cleanup)
    
    def p_request_reply(self, task_name, from_state=None, to_state=None, conditions=None, param_slots=[], address=None,
                        return_values=[], timeout=None, timeout_to_state=None, message_fields={}, description=None, cleanup=None):
        '''
        This is the same as p_send_task_assignment, except the caller will wait for the recipient to mark the message 'done' by calling 'succeed'
        
        return_values specifies a list of message fields to copy into the goal buffer upon return.
        If return_values is None, the caller does not wait for the recipient to finish processing the message.
        Any return_values not specified as outputs of this Task (to init) will be added to the list of slots to cleanup when the task finishes.
        
        timeout - specified in seconds.  After waiting this long for a response, give up.
        the return_values will not be set.  
        
        timeout_to_state - if a timeout is specified and expires, return to this state instead of to_state.
          If no timeout is specified, this is ignored.
                
        '''
        assert task_name is not None
        assert task_name != ""
        message_fields = message_fields.copy()
        message_fields[Opcode.ASSIGN_TASK.value] = task_name
        
        if from_state is None:
            from_state = self.prev_state        

        # make up a name for the state we'll be in while waiting for the message broker to send the ID of the new message.
        wait_for_returns = "AFTER-" + from_state + "-WAITING-FOR-RETURN-VALUES"
        
        actions=None
        if timeout:
            actions = "!bind! =ticks-to-wait (ticks-for-seconds {}) =goal> ticks-to-wait =ticks-to-wait +temporal> ticks 0 =goal>".format(timeout)

        self._add_to_cleanup(return_values)
        self._p_send_message(Opcode.REQUEST_REPLY, from_state=from_state, to_state=wait_for_returns, conditions=conditions, actions=actions, param_slots=param_slots, address=address, message_fields=message_fields, description=description, cleanup=cleanup)

        # now wait for the reply (i.e. return values) and clean up.
        
        returns = " " + " ".join(["{} ={}".format(r,r) for r in return_values]) # copy return values if any from visual-location buffer to goal buffer
        # this constrains us to wait only for a reply to the message we are currently waiting for.
        # this can become an issue if we previously gave up waiting on messages that timed out, and then they finally return while we're already waiting for some other message to return.
        goal_buffer_condition = "message_id =message_id"         
        actions = (" ticks-to-wait nil" if timeout else "") + returns
        self.p(from_state=wait_for_returns,
               conditions=goal_buffer_condition+" =visual-location> "+ Opcode.REPLY.value + returns,
               actions=actions,
               to_state=to_state, 
               description=description)

        # production for if it fails with a timeout.
        if timeout:
            timeout_conditions = "ticks-to-wait =ticks-to-wait =temporal>  >= ticks =ticks-to-wait".format(timeout)
            if timeout_to_state is None:
                timeout_to_state = to_state
            description = (description+"-" if description else "") + "TIMEOUT"
            self.p(from_state=wait_for_returns, to_state=timeout_to_state, conditions=timeout_conditions, actions="ticks-to-wait nil", description=description)
        
    def _p_send_message(self, opcode, from_state=None, to_state=None, conditions=None, actions=None, param_slots=[], address=None, message_fields={}, description=None, cleanup=None):
        '''
        Create productions to send the specified slots from the chunk in the goal buffer in a message via the message broker
        and then wait for the message id and store it in the message_id slot.
        
        message_fields specifies name/value pairs to be included in the message string.
        
        param_slots specifies the names of goal buffer slots.  The slot names/values will be included in the message string.
        Note, this will not fire unless all the slots are present in the goal buffer.
        For entries in param_slots that are tuples, the first element is the name of the goal buffer slot, and the second element is the name for this value in the message. 
        
        actions, if specified, will be taken when the message broker sends back the message-id.
        
        This is a private method (starts with underscore) because it creates a message that a recipient will not know how
        to handle unless additional fields are specified, such as Opcode.ASSIGN_TASK
        '''        

        if from_state is None:
            from_state = self.prev_state
        
        if to_state is None:
            to_state = "done"
        
        msg = opcode.value

        if address:
            msg += f' address {address}'
#            msg += f' address |{address}|'

        for k,v in message_fields.items():
            msg += " {} {}".format(k,v)

        def try_index(a, i):
            if isinstance(a, str): # strings can be indexed but we don't want to.
                return a
            try:
                return a[i]
            except:
                return a
            
        for p in param_slots:
            msg += " {} ~A".format(try_index(p,1)) # when a param_slot element can be indexed, element 0 is the slot name, element 1 is the message field name.
        
        # make up a name for the state we'll be in while waiting for the message broker to send the ID of the new message.
        wait_for_confirm = "AFTER-" + from_state + "-WAITING-FOR-MESSAGE-ID"
        
        # send off the message
        self.p_speak(msg, slots=[try_index(p,0) for p in param_slots], conditions=conditions, from_state=from_state, to_state=wait_for_confirm, description=description)

        # now wait for CONFIRM_SEND, which the message broker will send back right away.
        actions = "message_id =message_id" + (" "+actions if actions else "") # copy message_id from visual-location buffer to goal buffer
    
        self._add_to_cleanup(param_slots)

        self.p(from_state=wait_for_confirm,
               conditions="=visual-location> "+ Opcode.CONFIRM_SEND.value,
               actions=actions,
               to_state=to_state, 
               description=description,
               cleanup=cleanup)

    def p_get_message_field(self, field, index_slot=None, output_slot=None, message_id_slot="message_id", from_state=None, to_state=None, description=None):
        '''
        p_get_message_field retrieves the specified field from a MessageBroker message.
            In a loop, this allows the actr to 'read through' the message field by field instead of comitting the whole thing to memory.
            This does not contact the sender of the message for the information; it is answered directly by the python-side portion of the actr
            which accesses the messsage as stored in the messagebroker.  (akin to glancing at an email open on the actr's desktop)

        NOTE: if you use p_get_message field more than once in the same task, you must specify a 'description'
          so they will be distinct; otherwise instances of the the wait-for-field production will clash.

        field: The name of the field in the messsage to be retrieved, except missing the index on the end if index_slot is to be used.
        index_slot: if specified, this names a goal buffer slot whose value will be appended to the field.  This supports iterating through fields using an index,
           if the sender of the messsage named the fields with indexes.  E.g. 'value1', 'value2', 'value3'...
           It will be added to the list of slots to cleanup when this task exits, unless it is an output of this task.
        output_slot: the name of the goal buffer slot where the retrieved value will be stored.
          It will be added to the list of slots to cleanup when this task exits, unless it is an output of this task.
        message_id_slot: the name of the slot containing the id number of the messsage from which the field will be retrieved.
        '''
        
        to_wait = 'wait-for-field'
        if description:
            to_wait += '--' + description
        if index_slot:
            self.p_speak(Opcode.MESSAGE_FIELD_REQUEST.value+" message_id ~A message_field {}~A".format(field),
                         slots=[message_id_slot, index_slot],
                         from_state=from_state, to_state=to_wait, description=description)
        else:
            self.p_speak(Opcode.MESSAGE_FIELD_REQUEST.value+" message_id ~A message_field {}".format(field),
                         slots=[message_id_slot],
                         from_state=from_state, to_state=to_wait, description=description)
        
        
        #     MESSAGE_FIELD_REPLY = "messagebroker message_field_reply message_id =message_id message_field =message_field message_field_value =message_field_value"
        conditions = "{} =message_id =visual-location> ".format(message_id_slot)+ Opcode.MESSAGE_FIELD_REPLY.value
        
        self.p(conditions=conditions, actions=output_slot+" =message_field_value", to_state=to_state, description=description)
        
        self._add_to_cleanup(index_slot)
        self._add_to_cleanup(output_slot)

    def p_defer_message(self, message_id_slot="message_id", preconditions=[], from_state=None, to_state="cleanup", conditions=None, actions=None, description=None, utility=None, cleanup=None):       
        if actions == None:
            actions = ""
        actions += " defer-message T"

class HandleMessagesTask(ActrTask):
    '''
    HandleMessagesTask is a 'master task' that endlessly loops and watches the act-r display for orders to call subtasks by name.
    '''
    def __init__(self, main_task, bind_tasks):
        super().__init__("handle-messages", main_task=main_task)
        self.p(to_state="request-message", conditions=None, actions=None)
        self.p_speak(Opcode.REQUEST.value, to_state=Opcode.WAITING_FOR_MESSAGE.value)

        if main_task: # if this is the main task, then after handling one message, loop back to the start to get another.
            self.p(from_state="end", to_state="start")

        for t in bind_tasks:
            self.bind_task(t)

    def bind_task(self, actr_task):
        '''
        Create a production so this handle-messages task will call the specified subtask if its name and parameters appear on the act-r display device 
        task_params is a list of names of message fields that must be present in the message and will be copied into the goal buffer chunk.
        '''
        inputs = actr_task.inputs
        if inputs is None:
            inputs=[]
        
        # filter out message_id if manually specified because it is also included automatically and specifying it twice causes an error.
        # The reason to specify it manually is so it will be captured by ActrTask.p_trace_inputs, if that is desired.
        inputs = " ".join(["{} ={}".format(input, input) for input in inputs if input != "message_id"])
        
        match_message = "=visual-location> {} {}".format(Opcode.RECEIVE_TASK_ASSIGNMENT.value.replace("=taskname", actr_task.task_name), inputs)

        cleanup_task = "cleanup-"+actr_task.task_name
        
        self.p_subtask(from_state=Opcode.WAITING_FOR_MESSAGE.value, conditions=match_message,
                       subtask=actr_task.task_name, 
                       return_to_state=cleanup_task,
                       actions="message_id =message_id "+inputs,
                       description=actr_task.task_name)

        # if the actr sets the goal buffer slot defer-message

        # create a production to handle the case of deferring, rather than closing, the message.
        # note: this will only fire if the defer-to-message slot is set (which is what we want) because specifying it as a lot
        # for p_speak will result in it being included in the conditons. 
        defer_msg = Opcode.DEFER.value + " message_id ~A"
        self.p_speak(defer_msg,
                     slots="defer-to-message",
                     from_state=cleanup_task,
                     actions="defer-to-message nil", 
                     to_state="end",
                     description="deferred")

        # create a production to handle the normal case, where the task has set task-state to 'done'
        # and set the goal buffer slots corresponding to return values.
        close_msg = Opcode.CLOSE.value
        outputs = actr_task.outputs
        if outputs is None:
            outputs = []
        if len(outputs) > 0:
            close_msg += " "+" ".join(["{} ~A".format(r) for r in outputs])
        self.p_speak(close_msg,
                     conditions="defer-to-message nil", 
                     slots=outputs, from_state=cleanup_task, 
                     actions="message_id nil", # not using the cleanup parameter to p_subtask because we are done with this message_id now, even though the handle-messages task is not exiting. 
                     to_state="end")

class ActrMessagingPerson(ActrPerson):
    '''
    This is somebody whose activities are driven by sending/receiving messages to a MessageBroker.
    
    For a working example, see actr_messaging_person.ActrMessagingTest (TODO: update this reference, it's incorrect)
    
    '''

    def __init__(self, name, message_broker, actr_tasks=None, address=[], message_driven=True, simpy_env=None, enable_actr_trace=False, task_logger=None):
        '''
        address: a string (or iterable of strings) specifying the address(es) at which this person will receive messages.
          If the empty list (which is the default) the person's name will be their only address, although they can still
            receive messages that don't specify an address.
          If none, will not accept any message that has an address. 
          see messaging.AddressFilter for more information.

        actr_tasks: tasks the actr knows how to do.
          Each element is an instance of ActrTask or ActrMessageTask.
          ActrMessageTask instances can be triggered by sending a Message which has task_name==task.name,
            and a message field matching each input of the task, which will be copied to the goal buffer.

        message_driven: if true, creates productions that set the gaol buffer whenever it is empty to loop over handle-messages  
        '''
        
        actr_tasks = check_actr_tasks(actr_tasks)
        
        # the subset of actr_tasks that are ActrMessageTask instances
        message_tasks = [t for t in actr_tasks if isinstance(t, ActrMessageTask)]
        
        # if this actr is "message-driven", automatically start listening for messages
        hm = HandleMessagesTask(main_task=message_driven, bind_tasks=message_tasks)
            
        super().__init__(name, actr_tasks+[hm], simpy_env=simpy_env, enable_actr_trace=enable_actr_trace, task_logger=task_logger)
        self.message_broker = message_broker
        self.current_message = None
        
        # ActrMessagingPerson requires Simpy.  (The base class, ActrPerson, does not)
        assert(simpy_env)
        
        self.message_filter = None if address is None else AddressFilter(self.name) if len(address)==0 else AddressFilter(address)

    def handle_actr_speech(self, speech):
        '''
        This is called when the actr says something, which is how they send information or commands to the environment and other actrs.
        (Speech from other actrs does not trigger this, instead it gets translated into something this actr will see on their screen device.)
        
        If you override this, be sure to call this (super.handle_actr_speech) or else messages won't be processed. 
        
        override of base class method.
        '''
        # print(f'ActrMessagingPerson.handle_actr_speech by {self.name}: {speech}')
        
        def get_pairs_after(s):
            a = speech[len(s):].lstrip().split() # "opcode a b c d" -> ["a", "b", "c", "d"]
            return dict(zip(a[::2], a[1::2])) # create name=value pairs for dict using alternating name,value  {"a":"b", "c":"d"} 
        
        if speech.startswith(Opcode.REQUEST.value):
            self.handle_request_message()
        elif speech.startswith(Opcode.CLOSE.value):
            self.handle_close_message(get_pairs_after(Opcode.CLOSE.value))
        elif speech.startswith(Opcode.DEFER.value):
            self.handle_defer_to_message(get_pairs_after(Opcode.DEFER.value))
        elif speech.startswith(Opcode.SEND.value):
            self.handle_send_message(get_pairs_after(Opcode.SEND.value))
        elif speech.startswith(Opcode.REQUEST_REPLY.value):
            self.handle_request_reply(get_pairs_after(Opcode.REQUEST_REPLY.value))
        elif speech.startswith(Opcode.MESSAGE_FIELD_REQUEST.value):
            self.handle_message_field_request(get_pairs_after(Opcode.MESSAGE_FIELD_REQUEST.value))
        else:
            super().handle_actr_speech(speech)

    def handle_request_message(self):
        '''
        This means the actr is ready to receive a message.
        It is called from the dispatch thread of actr
        It must return promptly, but assign a message to the ACT-R Messaging Person when one becomes available.
        ''' 
        def send_message_to_actr():
            self.current_message = yield self.message_broker.get(self.message_filter)
            self.current_message.assignedTo = self
            args = dict(self.current_message.getLogAttributes())
            args['message_id'] = self.current_message._msg_id
#             print("{}: {} assigned message with priority {}".format(self.simpy_env.now, self.name, self.current_message.priority))
            self.show_on_screen(**args)
 
        self.simpy_env.process(send_message_to_actr())
 
    def handle_send_message(self, pairs):
        '''
        The actr calls this to send a message via the message broker.
        It is called from the dispatch thread of actr
        ''' 
        m = Message(self.simpy_env, **pairs)
        self.message_broker.put(m)
        self.show_on_screen(**string_to_dict(Opcode.CONFIRM_SEND.value.replace("=message_id", str(m._msg_id))))

    def handle_request_reply(self, pairs):
        '''
        The actr calls this to send a message via the message broker and wait until it is closed.
        The broker will promptly send a CONFIRM_SEND with the ID, then send the results at least 1 second (in simulation time) later.
        The reason for this delay is to give the actor a chance to see the CONFIRM_SEND before it is overwritten with the REPLY.
        It is called from the dispatch thread of actr.
        ''' 
        m = Message(self.simpy_env, **pairs)
        self.message_broker.put(m)
        self.show_on_screen(**string_to_dict(Opcode.CONFIRM_SEND.value.replace("=message_id", str(m._msg_id))))
        
        wait_until = self.simpy_env.now + 1
        
        def send_reply():
            yield m
            d = string_to_dict(Opcode.REPLY.value.replace("=message_id", str(m._msg_id)))
            for k,v in m.getLogAttributes():
                d[k]=v
            now = self.simpy_env.now # store in a variable so it doesn't change between the next couple lines of code - since we are running in the dispatch thread instead of the sim thread  
            if now < wait_until:
                yield self.simpy_env.timeout(wait_until - now) 
            self.show_on_screen(**d)
        self.simpy_env.process(send_reply())
                  
    def handle_message_field_request(self, pairs):
        # print("handle_message_field_request pairs: {}".format(pairs))
        m = self.message_broker.get_message_by_id(pairs["message_id"])
        reply = Opcode.MESSAGE_FIELD_REPLY.value
        reply = reply.replace("=message_id", str(m._msg_id))
        reply = reply.replace("message_field =message_field",  "message_field "+ActrPerson.actr_string(pairs["message_field"]))
        reply = reply.replace("message_field_value =message_field_value", "message_field_value "+ActrPerson.actr_string(str(getattr(m, pairs["message_field"]))))
        # print("handle_message_field_request {} replying: {}".format(pairs, reply))
        self.show_on_screen(**string_to_dict(reply))
    
    def handle_close_message(self, message_fields):
        '''
        The actr calls this to mark a message as closed.
        It is called from the dispatch thread of actr.
        Any additional message_fields are set in the message as it is closed.       
        '''
        self.current_message.time_closed = self.simpy_env.now
        self.current_message.message = "Completed by ACTR-R person {}".format(self.name)
#         print("{}: {}".format(self.simpy_env.now, self.current_message.message))
#         if self.current_message.getLogAttributes() is not None:
#             self.log_message(self.current_message)
        self.current_message.succeed(message_fields=message_fields)
        self.current_message = None
        
    def handle_defer_to_message(self, message_fields):
        '''
        Invoke Message.defer()
        It is called from the dispatch thread of actr.
        Any additional message_fields are set in the message as it is deferred.       
        '''
        
        self.message_broker.add_preconditions(self.current_message, message_fields['message_id'])
        
        self.current_message.defer()
        self.current_message = None
        
