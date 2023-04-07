'''
Created on Sep 14, 2020

@author: rgabbot
'''


'''
Created on Apr 7, 2020

@author: rgabbot
'''
import cogtasks
import unittest
from cogtasks.actr_person import ActrPerson, actr_eval, ActrTask
from cogtasks.actr_messaging_person import ActrMessagingPerson, ActrMessageTask
import actr
from cogtasks.rbblogger import RBBLogger
import simpy
import tempfile
from cogtasks.messaging import Message, MessageBroker, State, AddressFilter
import re
from random import randint

class Test(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        '''
        All the tests will share the lisp environment running actr, and a simpy environment.
        This does create some risk of the tests stepping on each other but restarting lisp between each one would be cumbersome.
        '''
#        cls.logger = RBBLogger({'runID':'test', 'realm':'people'}, file=sys.stdout)
        cls.logger = RBBLogger({'runID':'test', 'realm':'people'}, file="test.rbb")
        cls.env = simpy.Environment()
#         cls.unit = Unit(cls.env, cls.logger, "Default Unit", messagebroker=None)

    def test_echo(self):
        '''
        This test checks several aspects of basic functionality:
        - A model is sent to actr-r from python
        - Two different people with different names are instianted in act-r, and each is separately associated with a Python object (an EchoPerson instance)
        - running simpy (env.run()) also advances act-r and they advance by the same amount to stay in sync
        - Messages are sent to them using their visual location buffer.
        - They communicate back by speaking through the microphone device
        - Productions can be added to a model (echo2 in this case), so they don't need to be created in a single statement.  
          This allows for modular construction where a bundle of productions can be added to whichever models are appropriate. 
        '''
#         actr_eval("(clear-all)") # wipe out any previous model in act-r.  Problem is it also restarts time in act-r, but not simpy
        
        billy = EchoPerson("BILLY", actr_code=EchoPerson.code, simpy_env=self.env)
        billy.enable_trace = True
        bobby = EchoPerson("BOBBY", actr_code=EchoPerson.code, simpy_env=self.env)
        
        billy.show_on_screen(message="I am Billy") 
        bobby.show_on_screen(message="I am Bobby") 
        
        start = self.env.now
        end = start + 10
        self.env.run(until=end)
        self.assertEqual(self.env.now, end)
        self.assertEqual(actr.get_time(), end * 1000)

#         for person in [billy, bobby]:
#             print("{} said:".format(person.name), file=sys.stderr)
#             for s in person.speech:
#                 print(s, file=sys.stderr)

        self.assertEqual(billy.speech[0], "I AM BILLY")
        self.assertEqual(bobby.speech[0], "I AM BOBBY")

        billy.set_current_model()
        actr_eval(billy.code2)
        actr.spp("echo2", ":u", 1) # make echo2 take precedence over echo
        
        billy.show_on_screen(message="I am still Billy") 
 
        self.env.run(self.env.now+1)
 
        self.assertEqual(billy.speech[1], "2 I AM STILL BILLY") # the 2 at the start shows it was the new production that fired.

#         post_run_logging(groundTruth, network, aoc_unit)
        time = actr.get_time() # todo: is this in seconds or milliseconds?
        ActrPerson.cleanup_everybody(time)

    def test_increment(self):
        '''
        Test ActrTask.p_increment
        '''
        t = ActrTask("IncrTask", main_task=True)
        t.p(actions="n 1", to_state="s1")
        t.p_increment("n") 

        p = ActrPerson("I", t)

        self.env.run(self.env.now+1)

        self.assertEqual(p.get_goal_slot("n"), 2)

    def test_if_then_else(self):
        
        def test(slot_a, op, slot_b=None, value_b=None):
            t = ActrTask("task", main_task=True)
            actions = "a {}".format(slot_a) # store a in slot
            if slot_b:
                actions += " b {}".format(slot_b)
                t.p(actions=actions, to_state="s1")
                t.p_if_then_else(cmp=op, slot_a="a", slot_b="b", to_state="true", else_to_state="false")
            else: # b specified as value_b
                t.p(actions=actions, to_state="s1")
                t.p_if_then_else(cmp=op, slot_a="a", value_b=value_b, to_state="true", else_to_state="false")
                
            t.p(from_state="true", actions="result YES")
            t.p(from_state="false", actions="result NO")
            p = ActrPerson("P2", t, enable_actr_trace=False)
            self.env.run(self.env.now+1)
            result = p.get_goal_slot("result")
            p.delete_model()
            if result=="YES":
                return True
            if result=="NO":
                return False
            assert(False)
            
        self.assertTrue(test(1, "=", 1))
        self.assertFalse(test(1, "=", 2))

        self.assertTrue(test(1, "<", 2))
        self.assertFalse(test(1, "<", 1))
        
        self.assertTrue(test(2, ">", 1))
        self.assertFalse(test(1, ">", 1))
        
        self.assertTrue(test(0, "<=", 1))
        self.assertTrue(test(1, "<=", 1))
        self.assertFalse(test(2, "<=", 1))
        
        self.assertFalse(test(0, ">=", 1))
        self.assertTrue(test(1, ">=", 1))
        self.assertTrue(test(2, ">=", 1))

        # try specifiying b as a value
        self.assertFalse(test(0, ">=", value_b=1))
        self.assertTrue(test(1, ">=", value_b=1))
        self.assertTrue(test(2, ">=", value_b=1))
        
        self.assertFalse(test(2, "=", value_b="nil"))
        self.assertTrue(test(2, "-", value_b="nil"))

    def test_for_loop(self):
        ''' make a for loop from if_then_else and increment '''
        t = ActrTask("task", main_task=True)
        t.p(actions="i 1 n 5", to_state="loop")
        t.p_if_then_else("<=", "i", "n", to_state="comment", else_to_state="cleanup")
        t.p_speak("i=~A", slots=["i"], to_state="increment")
        t.p_increment("i", to_state="loop")
        t.p_speak("cleanup", from_state="cleanup")

        env = self.env
        class P(ActrPerson):
            ''' this is an actr person who collects everything they say into self.speech '''
            def __init__(self):
                self.speech=[]
                super().__init__("P3", t, simpy_env = env, enable_actr_trace=False)
            
            def handle_actr_speech(self, s):
                self.speech.append(s)
        
        p = P()
        
        self.env.run(self.env.now+5)
#         result = p.get_goal_slot("result")
        actr_eval("(delete-model {})".format(p.name))
        
        self.assertEqual(p.speech, ["i=1", "i=2", "i=3", "i=4", "i=5", "cleanup"])

    def test_from_files(self):
        '''
        Create an actr model with parts are read in from separate files.
        The purpose of this is to test having sets of productions in a file so they can be shared, i.e. loaded into any specific model as needed.
        
        In this test the contents of those files will come from the class attributes EchoPerson.code and EchoPerson.code2,
        but that is just so we don't need to keep those files around.  In practice keeping the lisp code in .lisp 
        files (instead of strings in python code) is better if the amount of code is significant, so it can be
        loaded into lisp without involving python, edited in a lisp-specific editor, and so on.
        '''
#         actr_eval("(clear-all)") # wipe out any previous model in act-r.  Problem is it also restarts time in act-r, but not simpy

        joe = EchoPerson("JOE", self.env)
        judy = EchoPerson("JUDY", self.env)
        for person in [joe, judy]:
#             person.enable_trace = True
            with tempfile.NamedTemporaryFile(mode="w") as tmp:
                print("(with-model {} {})".format(person.name, person.code), file=tmp)
                tmp.flush() # this IS necessary
                actr.load_act_r_model(tmp.name)

        # now load echo2 ONLY into Joe, even though it wasn't the last model loaded.
        joe.set_current_model()
        with tempfile.NamedTemporaryFile(mode="w") as tmp:
            print(joe.code2, file=tmp)
            tmp.flush() # this IS necessary
            actr.load_act_r_code(tmp.name) # load_act_r_model also works here, I don't know what the difference is.
            actr.spp("echo2", ":u", 1) # make echo2 take precedence over echo
    
        joe.show_on_screen(message="I am Joe") 
        judy.show_on_screen(message="I am Judy") 

        start = self.env.now
        end = start + 10
        self.env.run(until=end)
        self.assertEqual(self.env.now, end)
        self.assertEqual(actr.get_time(), end * 1000)

        print(joe)
        print(judy)

#         for person in [joe, judy]:
#             print("{} said:".format(person.name), file=sys.stderr)
#             for s in person.speech:
#                 print(s, file=sys.stderr)
                
        self.assertEqual(joe.speech[0], "2 I AM JOE")
        self.assertEqual(judy.speech[0], "I AM JUDY")

    def test_actr_task(self):
        '''
        Use ActrTask to make a simple task - a set of productions that moves through a sequence of states.
        '''
        
        #actr_eval("(clear-all)")
        
        class Patty(ActrPerson):
            def __init__(self, simpy_env):
                atask = ActrTask("TestTask", main_task=True)
                atask.p(to_state="state1") 
                atask.p(to_state="state2") 
                atask.p(to_state="state3") 
                atask.p()
                super().__init__("PATTY", atask, simpy_env=simpy_env, enable_actr_trace=False)
                self.fired = []
            def actr_trace(self, actr_time, actr_module, actr_cmd, actr_args):
                if actr_cmd == "PRODUCTION-FIRED":
                    self.fired.append(actr_args)
                super().actr_trace(actr_time, actr_module, actr_cmd, actr_args)

        p = Patty(self.env)
        start = self.env.now
        end = start + 10
        self.env.run(until=end)
        
        self.assertEqual(p.fired, [
            "TESTTASK--MAIN", # created because main_task=True was specified.
            "TESTTASK--START", # because the first call to production() didn't specify from_state, 'start' was assumed.
            "TESTTASK--STATE1", # thereafter, since from_state was not specified, it is assumed to be the to_state of the previous production.
            "TESTTASK--STATE2",
            "TESTTASK--STATE3"])

    def test_production_utilities(self):
        '''
        specify utilities for productions to control the order in which they are selected.
        '''
        class Util(ActrPerson):
            def __init__(self):
                t = ActrTask("U", main_task=True)
                t.p(to_state="start", description="A", conditions="- A T", actions="A T", utility=.1) 
                t.p(to_state="start", description="B", conditions="- B T", actions="B T", utility=2) 
                t.p(to_state="start", description="C", conditions="- C T", actions="C T", utility=.5) 
                # negative utility will not be fired even though the utility threshold :ut is nil.
                # the documentation says any "all productions will be considered" if ut is nil but this doesn't appear to be the case. 
                # :iu (initial utility) is the default utility value and defaults to 0, which means you can't assign a lower-than-default utility value. 
                t.p(to_state="start", description="D", conditions="- D T", actions="D T", utility=-1) 
                t.p(to_state="done", description="done", utility=0)
                # sgp er t = "set global parameter" "enable randomness".  Used to break ties (in this case they all have different utility so it doesn't make a difference.
                super().__init__("UTILITY", actr_tasks=t, actr_code="(sgp :er t)")
                self.fired = []
            def actr_trace(self, actr_time, actr_module, actr_cmd, actr_args):
                if actr_cmd == "PRODUCTION-FIRED":
                    self.fired.append(actr_args)

        p = Util()
        start = self.env.now
        end = start + 10
        self.env.run(until=end)
        
        self.assertEqual(p.fired, ['U--MAIN--A',  # created because main_task=True was specified and A was created first. 
                                    'U--START--B', # highest utility first
                                    'U--START--C', 
                                    'U--START--A', # lowest (.5) last
                                    'U--START--DONE'])

    def test_actr_subtask(self):
        '''
        Use ActrTask to make a task that calls a second task, after which the first task resumes.
        '''
        
        class QBert(ActrPerson):
            def __init__(self, env):
                
                task_a = ActrTask("TASK_A", main_task=True)
                task_b = ActrTask("TASK_B")
                
                task_a.p_subtask(subtask = task_b.task_name, return_to_state="after_b")
                task_a.p()

                task_b.p() # defines the simplest task - since from_state and to_state are not specified it triggers on 'start' and transitions straight to 'done'
                                
                super().__init__("QBERT", actr_tasks=[task_a, task_b], enable_actr_trace=True, simpy_env=env)
                self.fired = []
                
            def actr_trace(self, actr_time, actr_module, actr_cmd, actr_args):
                if actr_cmd == "PRODUCTION-FIRED":
                    self.fired.append(actr_args)
                super().actr_trace(actr_time, actr_module, actr_cmd, actr_args)

        p = QBert(self.env)
        start = self.env.now
        end = start + 10
        self.env.run(until=end)
        
        # note this is not actually all the productions fired in ACT-R
        # actr_person.dispatch_actr_trace discards the 'boilerplate' productions for tasks, e.g. maintaining the call stack.
        self.assertEqual(p.fired, [
            "TASK_A--MAIN",  # because main_task=True passed to task_a constructor
            "TASK_A--START",
            "TASK_B--START", # great - a called b
            "TASK_A--AFTER_B" # then returned back to a
            ])
  

    def test_actr_subtask__rename_slots_after(self):
        '''
        This tests for a conflict between save_slots and rename_slots_after that cropped up.
        
        Specifically, Task_A has a slot "x" and needs to preserve its value across a call to Task_B,
          which returns a value through slot "x", which Task_A will expect to access as "y"
          
        i.e.:
        def task_b():
            x=2
            return x
        
        def task_a():
            x=1
            y=task_b()
            assert(x==1)
            assert(y==2)
        '''
        
        class P(ActrPerson):
            def __init__(self, env):
                task_a = ActrTask("TASK_A", main_task=True)
                task_b = ActrTask("TASK_B")
                task_a.p(actions="x 1", to_state="call_subtask")
                task_a.p_subtask(subtask = task_b.task_name, save_slots=["x"], rename_slots_after={"x":"y"}, return_to_state="done")
                task_b.p(actions="x 2")
                super().__init__("P4", [task_a, task_b], simpy_env=env)
                
        p = P(self.env)
        self.env.run(until=self.env.now+10)
        self.assertEqual(p.get_goal_slot("x"), 1)
        self.assertEqual(p.get_goal_slot("y"), 2)
        p.delete_model()

    def test_cleanup(self):
        '''
        Test the 'cleanup' parameter of ActrTask, which p_cleanup uses to delete a list of slots from the goal buffer before the task exits. 
        '''
        class P(ActrPerson):
            def __init__(self, env):
                t = ActrTask("T", main_task=True)
                t.p(actions="a 1 b 2 c 3 d 4", cleanup="a", to_state="s2") # specify 1 slot
                t.p(cleanup=["b", "c"], to_state="cleanup") # specify array of slots
                t.p_cleanup()
                super().__init__("P5", t, simpy_env=env)

        p = P(self.env)
        self.env.run(until=self.env.now+10)
        self.assertEqual(p.get_goal_slot("a"), None)
        self.assertEqual(p.get_goal_slot("b"), None)
        self.assertEqual(p.get_goal_slot("c"), None)
        self.assertEqual(p.get_goal_slot("d"), 4)
        p.delete_model()

  
    def test_minimal_send_receive_task(self):
        '''
        One person (sender) sends a message to another.
        This tests sending, receiving and addressing.
        It's  simple, with an emphasis on showing how to send a message rather than testing everything.  (test_send_receive_task below does that)
        '''
        task_name = "mytask"
        
        class Sender(ActrMessagingPerson):
            '''
            Send different messages to two recipients, 
            The messages includes fields from both param_slots (i.e. goal buffer slots), and kwargs arguments to p_send_task_assignment.
            Then the sender 'speaks' the ID of resulting message so we can assert it was received by the actr, and matches the Message instance in the MessageBroker. 
            '''
            def __init__(self, name, message_broker, simpy_env):
                task = ActrMessageTask("sendtask", main_task=True)
                task.p_send_task_assignment(task_name, address="MY_ADDRESS", message_fields={"foo":"bar"})
                super().__init__(name, message_broker, task, message_driven=False, simpy_env=simpy_env)
       
        class Receiver(ActrMessagingPerson):
            ''' The Task performed by the receiver is simply to speak out the values of the message fields, and the message_id
            '''
            def __init__(self, name, message_broker, simpy_env):
                task = ActrMessageTask(task_name, inputs=["foo"])
                task.p_speak("Comment: message_id ~A: foo ~A", slots=["message_id", "foo"])
                super().__init__(name, message_broker, actr_tasks=task, message_driven=True, simpy_env=simpy_env)       

        mb = MessageBroker(self.env)
        s = Sender("THE_SENDER", mb, self.env)
        r = Receiver("MY_ADDRESS",  mb, self.env)
        
        self.env.run(self.env.now+10) 
        
        self.assertEqual(mb.items[0]._msg_state, State.CLOSED) # this verifies the message got through, and prompted the receiver to process and mark it CLOSED.
    
    def test_send_receive_task(self):
        '''
        One person (sender) sends a message to two others (receiver1 and receiver2)
        This tests sending, receiving, addressing, and message priorities.
        '''
        task_name = "say-hi"
        
        class CaptureCommentsPerson(ActrMessagingPerson):
            ''' record my comments.  
                This is done only for assertion checking - it's not required to send/receive messages. '''
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.comments=[]
            def handle_actr_speech(self, speech):
                if speech.startswith("Comment: "):
                    self.comments += [speech]
                else:
                    super().handle_actr_speech(speech)

        recipients = ["RECEIVER1", "RECEIVER2"]
        NUM_MSG=6
        class Sender(CaptureCommentsPerson):
            '''
            Send different messages to two recipients, 
            The messages includes fields from both param_slots (i.e. goal buffer slots), and message_fields arguments to p_send_task_assignment.
            Then the sender 'speaks' the ID of resulting message so we can assert it was received by the actr, and matches the Message instance in the MessageBroker. 
            '''
            def __init__(self, name, message_broker, simpy_env):
                task = ActrMessageTask("send-task-assignment", main_task=True)
                for i in range(0,NUM_MSG):
                    priority=-i
                    j = i%len(recipients) # recipient index; 0 for Reciever1, 1 for Receiver2
                    i=str(i)
                    task.p(actions="slot1 value"+i, to_state="send"+i) # load some values into slots in the goal buffer to try sending them out in a message
                    task.p_send_task_assignment(task_name, param_slots=["slot1"], address=recipients[j], to_state="say_id_"+i, message_fields={"msg_field": "{}-{}".format(recipients[j],i), "priority":priority})
                    task.p_speak("Comment: message "+i+" got id ~A", ["message_id"], to_state="prepare_msg_"+i)
                task.p() # this just transitions the sender from whatever previous state to 'done'
                super().__init__(name, message_broker, actr_tasks=task, message_driven=False, simpy_env=simpy_env)
       
        class Receiver(CaptureCommentsPerson):
            ''' The Task performed by the receiver is simply to speak out the values of the message fields, and the message_id, so we can check them.
            '''
            def __init__(self, name, message_broker, simpy_env):
                # message_id is not specified as an input because it's not supplied by the sender, it's assigned by messagebroker. 
                task = ActrMessageTask(task_name, inputs=["slot1", "msg_field"])
                task.p_speak("Comment: message_id ~A: slot1 ~A msg_field ~A", slots=["message_id", "slot1", "msg_field"])
                super().__init__(name, message_broker, actr_tasks=task, message_driven=True, simpy_env=simpy_env)       
                
        first_message_id = Message.next_msg_id

        mb = MessageBroker(self.env)
        s = Sender("SENDER", mb, simpy_env=self.env)
        
        self.env.run(self.env.now+100) # first run just the sender, giving them time to send all the orders before any are taken out.  Otherwise the first one is done first, instead of priority order.
        
        r1 = Receiver("RECEIVER2", mb, simpy_env=self.env)
        self.env.run(self.env.now+2) # stagger the workers a bit to make the times unequal.  giving worker 2 a head start, in combination with using -i for priority, makes the start times in reverse order of creation order.
        r2 = Receiver("RECEIVER1", mb, simpy_env=self.env)
        self.env.run(self.env.now+200)
        
        # print(mb)
        
        # now to check the results
        
#         print(mb)

        # verify people got their own messages
        for r in [r1,r2]:
            for c in r.comments:
                self.assertTrue(r.actr_name() in c) # we packed the recipient name into the msg_field, so it should come through, but in all caps.

        for i in range(0, len(mb.items)):
            a = mb.items[i]
            self.assertEqual(a._msg_state, State.CLOSED) # verify  all jobs got done

            # assert timing / ordering of messages processed
            self.assertLess(a._msg_time_accepted, a._msg_time_closed) # verify time_accepted and time_closed were assigned.
            
            if i < len(mb.items)-1:
                b = mb.items[i+1]
                self.assertLess(a._msg_time_submitted, b._msg_time_submitted) # verify messages were submitted in order
                self.assertGreater(a._msg_time_accepted, b._msg_time_accepted) # verify messages were handled in reverse order, because priority was assigned as -i, and worker2 started a little sooner. 
                self.assertTrue(b._msg_time_accepted <= a._msg_time_accepted <= b._msg_time_closed) # verify the two workers worked simultaneously, not serially - a was started sometime between when b started and finished.  

        # verify message content got to the recipient, using the particular constraint we set up between message id (order of creation) and parameter values.
        comments = r1.comments + r2.comments
        self.assertEqual(NUM_MSG, len(comments)) # all messages got through
        for c in comments:
            m = re.search("message_id (\d+)", c)
            id = m.group(1)
            n = str(int(id)-first_message_id)
            self.assertTrue(re.search("slot1 VALUE"+n, c)) # verify param_slots were sent (but capitalized)
            self.assertTrue(re.search("msg_field RECEIVER[12]-"+n, c)) # verify kwargs were sent (but capitalized)
    
    def test_request_reply(self):
        '''
        In this test a caller makes a synchronous request from another person - they send a task and then wait for a response before continuing
        '''
        class Multiplier(ActrMessagingPerson):
            def __init__(self, name, message_broker, simpy_env):
                task = ActrMessageTask("multiply", inputs=["a", "b"], outputs=["c"])
                task.p_bind_slot("c", "* =a =b")
                super().__init__(name, message_broker, message_driven=True, actr_tasks=task, enable_actr_trace=False, simpy_env=simpy_env)       

        mb = MessageBroker(self.env)
        m = Multiplier("MULTIPLIER", mb, self.env)
        _self = self

        class Caller(ActrMessagingPerson):
            def __init__(self, name, message_broker, simpy_env):
                task = ActrMessageTask("ask_for_answers", main_task=True)
                for i in range(0,10):
                    (a,b)=(randint(0,10), randint(0,10))
                    task.p_request_reply("multiply", to_state="print{}".format(i), address=m.name, return_values=["c"], message_fields={"a":a, "b":b})
#                     if(i==0):
#                         print(task)
                    task.p_speak("Comment: the multiplier says {} * {} = ~A".format(a,b), slots=["c"], to_state="multiply{}".format(i+1))
                super().__init__(name, message_broker, message_driven=False, actr_tasks=task, enable_actr_trace=False, simpy_env=simpy_env)
                self.num_checked = 0

            def handle_actr_speech(self, speech):
                '''
                The caller will announce the results received, which this function monitors to check the results.
                This is just checking code and not necessary for the call itself.
                '''
                m = re.search("(\d+) \* (\d+) = (\d+)", speech)
                if m:
                    _self.assertEqual(int(m.group(1))*int(m.group(2)), int(m.group(3)))
                    self.num_checked += 1
                else:
                    super().handle_actr_speech(speech)

        c = Caller("CALLER", mb, simpy_env=self.env)
        
        self.env.run(self.env.now+100)
#         print(mb)
        self.assertEqual(c.num_checked, 10)
    
    
    def test_request_reply_from_device(self):
        '''
        In this test a caller makes a synchronous request from a non-actr entity - a counter in this case.
        This shows how an actr can communicate with other devices or entities written in python.
        '''

        mb = MessageBroker(self.env)
        _self = self
              
        def counter():
            i=0
            while True:
                job = yield mb.get(filter =  AddressFilter("counter"))
                _self.assertEqual(job.assign_task, "whatever") # normally this would be used to tell the recipient what to do, but the counter only does one thing so it's ignored.
#                 print("counter got message: {}".format(job))
                i+=1
                job.succeed(True, {"count":i})
        self.env.process(counter())


        class Caller(ActrMessagingPerson):
            def __init__(self, name, message_broker, simpy_env):
                task = ActrMessageTask("test_counter", main_task=True)
                for i in range(0,10):
                    task.p_request_reply("whatever", to_state="print{}".format(i), address="counter", return_values=["count"])
                    task.p_speak("Comment: the counter returned ~A", slots=["count"], to_state="request-reply{}".format(i+1))
                super().__init__(name, message_broker, message_driven=False, actr_tasks=task, enable_actr_trace=False, simpy_env=simpy_env)
                self.count = 0

            def handle_actr_speech(self, speech):
                '''
                The caller will announce the results received, which this function monitors to check the results.
                This is just checking code and not necessary for the call itself.
                '''
                m = re.search("counter returned (\d+)", speech)
                if m:
                    self.count += 1
                    _self.assertEqual(self.count, int(m.group(1)))
#                     print("{}: {}".format(self.env.now, speech))
                else:
                    super().handle_actr_speech(speech)

        c = Caller("A_CALLER", mb, simpy_env=self.env)
        
        self.env.run(self.env.now+100)
#         print(mb)
        self.assertEqual(c.count, 10)
    
    def test_request_reply_from_person(self):
        '''
        In this test, a device sends a message to a person once per timestep and waits for their response.
        The person is not able to keep up with a message rate of 1 per second, so the number of assigned (but not completed) messages would grow without bound.
        '''
        mb = MessageBroker(self.env)

        x0 = -10
        n = 20
        t0 = self.env.now
        
        def machine(results):
            for x in range(x0, x0+n):
                m = Message(env=self.env, assign_task="positive", x=x)
                mb.put(m)
                yield(m)
                results.append((self.env.now, x, m.y))
                yield self.env.timeout(1)

        results = []
        self.env.process(machine(results))

        class OperatorPerson(ActrMessagingPerson):
            def __init__(self, name, message_broker, simpy_env):
                task = ActrMessageTask("positive", inputs=["x"], outputs=["y"])
                task.p_if_then_else(">", "x", value_b=0, to_state="return_true", else_to_state="return_false")
                task.p(from_state="return_true", actions="y T")
                task.p(from_state="return_false", actions="y F")
                super().__init__(name, message_broker, message_driven=True, actr_tasks=task, enable_actr_trace=False, simpy_env=simpy_env)

        op = OperatorPerson("OP2", mb, self.env)

        self.env.run(self.env.now+100)

        self.assertEqual(len(results), n)
        t_prev = None
        for t, x, y in results:
            if x > 0:
                self.assertEqual(y, "T")
            else:
                self.assertEqual(y, "F")
            if t_prev is not None:
                # self.assertEqual(t_prev+1, t) # this test will not pass unless the actr is able to handle 1 message per second (the rate at which messages were sent) which it cannot!
                pass
            t_prev = t
        
        print(results)

    def test_monitoring(self):
        '''
        Update the actor's monitor mutiple times per second.  If the actr notices a number greater than zero they press a button.
        Note, this does not use the message broker, so if the actr falls behind 
        (doesn't finish processing one stimulus before the next is presented) it will simply be disregarded.
        '''
        hz = 3 # trials per second
        x0 = -10
        n = 30
        t0 = self.env.now

        class OperatorPerson(ActrPerson):
            def __init__(self, name, simpy_env):
                task = ActrMessageTask("positive", main_task=True)
                task.p(from_state="start", to_state="decide", conditions="=visual-location> x =x", actions="x =x")
                task.p_if_then_else(">", "x", value_b=0, from_state="decide", to_state="alert", else_to_state="start")
                task.p_speak("~A is positive", slots=["x"], from_state="alert", to_state="start")
                super().__init__(name, task, enable_actr_trace=False)
                self.results =[]
                self.env=simpy_env
            
            def handle_actr_speech(self, speech):
                self.results.append((self.env.now, speech))
                # here the code could do something like turn off the machine,
                # if the operator is supposed to be monitoring for positive values.
        
        op = OperatorPerson("OP", self.env)
        
        def machine(operator):
            for x in range(x0, x0+n):
                operator.show_on_screen(x=x)
                yield self.env.timeout(1.0/hz)
        self.env.process(machine(op))
        
        self.env.run(self.env.now+100)
    
        print(op.results)
    
    def test_request_reply_with_timeout(self):
        '''
        In this test a caller makes a synchronous request from a non-actr entity - a counter in this case.
        This shows how an actr can communicate with other devices or entities written in python.
        '''

        mb = MessageBroker(self.env)
        _self = self
              
        def timer():
            while True:
                job = yield mb.get(filter =  AddressFilter("timer"))
#                 print("for this job I will sleep for {} seconds".format(job.seconds))
                yield _self.env.timeout(float(job.seconds))
                job.succeed()
        self.env.process(timer())


        class Caller(ActrMessagingPerson):
            def __init__(self, name, message_broker, simpy_env):
                

                self.timeout = 10
                self.tests_completed = 0

                task = ActrMessageTask("test-timeout", inputs=["seconds"])
                task.p_speak("~A start ~A", slots=["mp-time","seconds"], to_state="request-reply")
                task.p_request_reply("whatever", to_state="success", address="timer", param_slots=["seconds"], timeout=self.timeout, timeout_to_state="timed-out")
                task.p_speak("~A finish ~A", slots=["mp-time","seconds"], from_state="success", to_state="done")
                task.p_speak("~A timeout ~A", slots=["mp-time","seconds"], from_state="timed-out", to_state="done")

                super().__init__(name, message_broker, actr_tasks=task, message_driven=True, enable_actr_trace=False, simpy_env=simpy_env)

            def handle_actr_speech(self, speech):
                '''
                The caller will announce the results received, which this function monitors to check the results.
                This is just checking code and not necessary for the call itself.
                '''
                m = re.search("([\d\.]+) (start|finish|timeout) ([\d\.]+)", speech)
                if m is None:
                    super().handle_actr_speech(speech)
                    return

                # print(speech)
                (t, event, sleep) = m.groups()
                t = float(t)
                sleep = float(sleep)
                
                if event == "start":
                    self.start = t
                    return

                duration = t - float(self.start)
                
                if sleep > self.timeout: # it should fail if we try to sleep longer than the timeout period.
                    _self.assertEqual("timeout", event)
#                     print("Tried to sleep for {} so I timed out after {}, which should be close to {}".format(sleep, duration, self.timeout))
                else:
                    _self.assertEqual("finish", event)
#                     print("Slept for {} which should be close to {}".format(duration, sleep))
                    
                self.tests_completed += 1
                
                

        c = Caller("TIMER-CALLER", mb, simpy_env=self.env)
        
        sleeptimes = [5, 15, 6, 17]
        
        for s in sleeptimes:
            mb.put(Message(env=self.env, assign_task="test-timeout", seconds=s, address=c.name))
        
        self.env.run(self.env.now+200)
#         print(mb)

        self.assertEqual(c.tests_completed, len(sleeptimes))
    
    def test_multiple_subtasks(self):
        '''
        This exercises act-r conflict resolution by having multiple subtasks required to complete a task, but with no ordering among them.
        '''
        
        subtasks_done = []
        NUM_SUBTASKS=4
        
        def msg(i):
            return "Comment: I finished subtask "+str(i)
        
        class Worker(ActrPerson):
            def __init__(self):
                maintask = ActrMessageTask("main-task", main_task=True)
                tasks = [maintask]
                code = "(sgp :er t)" # "set-global-parameter enable-randomness true.  This makes the productions fire in nondeterministic order. 
                
                # define some meaningless subtasks
                for i in range(1,NUM_SUBTASKS+1):
                    subtask_name = "subtask"+str(i)

                    maintask.p_subtask(from_state="start", return_to_state="start", subtask=subtask_name, conditions=subtask_name+"done nil", actions=subtask_name+"done t", description=str(i))
                    
                    subtask = ActrMessageTask(subtask_name)
                    for j in range(1,4):
                        subtask.p(to_state="state"+str(j))
                    subtask.p_speak(msg(i))
                    tasks.append(subtask)
                    
                super().__init__("SUBTASKER", actr_tasks=tasks, actr_code=code)
            def handle_actr_speech(self, speech):
                if "I finished subtask" in speech:
                    subtasks_done.append(speech)
                else:
                    super().handle_actr_speech(speech)

        w = Worker()

        # w.enable_actr_trace = True
        # w.enable_lisp_console_output(True)

        self.env.run(self.env.now+100)

#         print(w.actr_eval("(printed-buffer-chunk 'goal)"))        
#         print(subtasks_done)
        
        # ensure every subtask was completed but none more than once.
        self.assertEqual(len(subtasks_done), NUM_SUBTASKS)
        for i in range(1,NUM_SUBTASKS+1):
            self.assertTrue(msg(i) in subtasks_done)
  
    def test_wait(self):
        '''
        test using the temporal module to do nothing for approximately a specified number of seconds.
        '''
        _self = self
        class Sleeper(ActrPerson):
            def __init__(self):
                driver = ActrTask("driver", main_task=True)
                self.times = [0.1, 1, 2.5, 5, 10, 100]
                self.total_of_ratios = 0.0
                
                i=0
                for t in self.times:
                    driver.p_speak("~A before waiting {}".format(t), slots=["mp-time"], to_state="wait{}".format(i))
                    driver.p_wait(t, to_state="stop{}".format(i))
                    driver.p_speak("~A after waiting {}".format(t), slots=["mp-time"], to_state="start{}".format(i+1))
                    i += 1
                
#                print(driver)
                super().__init__("SLEEPER", driver, enable_actr_trace=False)

            def handle_actr_speech(self, speech):
                m = re.search("([\d\.]+) (before|after) waiting ([\d\.]+)", speech)
                if not m:
                    super().handle_actr_speech(speech)
                elif m.group(2) == "before":
                    self.start_time = float(m.group(1))
                else:
                    _self.assertEqual("after", m.group(2))
                    tried_time = float(m.group(3))
                    actual_time = float(m.group(1))-self.start_time
                    ratio = tried_time / actual_time
#                     print("Tried to wait {}; actually waited {}; ratio={}".format(tried_time, actual_time, ratio))
                    self.total_of_ratios += ratio
                    
        s = Sleeper()
        self.env.run(self.env.now+500)
        
        # ensure the time waited is at least sort of close.
        # i.e. the average of actual time / target time was between .5 and 1.5
        # Note, there is no strong guarantee this assertion will or should hold, since the temporal module is inaccurate by design.
        self.assertTrue(.5 < s.total_of_ratios / len(s.times) < 1.5)

    def test_get_message_field(self):
        '''
        test ActrMessageTask.p_get_message_field(self, field, index_slot=None, output_slot=None, message_id_slot="message_id", from_state=None, to_state=None, description=None)
        '''
        t = ActrMessageTask("test_get_field")
        t.p_get_message_field("a", output_slot="x")

        mb = MessageBroker(self.env)
        p = ActrMessagingPerson("P6", mb, actr_tasks=t, message_driven=True, simpy_env=self.env, enable_actr_trace=False)

        mb.put(Message(env=self.env, assign_task=t.task_name, a=123))        

        self.env.run(self.env.now+100)
        self.assertEqual(p.get_goal_slot("x"), 123)


    def test_get_message_field_with_index(self):
        '''
        test ActrMessageTask.p_get_message_field(self, field, index_slot=None, output_slot=None, message_id_slot="message_id", from_state=None, to_state=None, description=None)
        '''
        t = ActrMessageTask("test_get_field")
        t.p(actions="index 1", to_state="get")
        t.p_get_message_field("a", index_slot="index", output_slot="x")

        mb = MessageBroker(self.env)
        p = ActrMessagingPerson("P7", mb, actr_tasks=t, message_driven=True, enable_actr_trace=False, simpy_env=self.env)

        mb.put(Message(env=self.env, assign_task=t.task_name, a1=123))        

        self.env.run(self.env.now+100)
        self.assertEqual(p.get_goal_slot("x"), 123)

    def test_get_message_field_with_indexes(self):
        '''
        test ActrMessageTask.p_get_message_field(self, field, index_slot=None, output_slot=None, message_id_slot="message_id", from_state=None, to_state=None, description=None)
        '''
        t = ActrMessageTask("test_get_field")
        t.p(actions="index 1", to_state="get1")
        t.p_get_message_field("a", index_slot="index", output_slot="x", to_state="prepare2")

        t.p(actions="index 2", to_state="get2")
        # note: since we're calling p_get_message_field twice to make 2 productions (that is, not one production in a loop)
        # we must specifify a 'description' to distinguish them.
        t.p_get_message_field("b", index_slot="index", output_slot="y", description='second')

        mb = MessageBroker(self.env)
        p = ActrMessagingPerson("P8", mb, actr_tasks=t, message_driven=True, enable_actr_trace=False, simpy_env=self.env)

        mb.put(Message(env=self.env, assign_task=t.task_name, a1=123, b2=234))

        self.env.run(self.env.now+100)

        print(mb)

        self.assertEqual(123, p.get_goal_slot("x"))
        self.assertEqual(234, p.get_goal_slot("y"))

    def test_get_message_fields_with_loop(self):
        '''
        Receive a message that contains a list of items, and iterate through them using a loop.
        The message specifies the number of elements in a field named 'n',
        and the elements in fields named a0, a1, a2...
        '''

        task_name = 'loop_message_fields'

        # create a message containing an array
        mb = MessageBroker(self.env)
        array = {f'a{i}':i*10 for i in range(5)} # {'a0': 0, 'a1': 10, 'a2': 20, 'a3': 30, 'a4': 40}
        mb.put(Message(env=self.env, assign_task=task_name, n=len(array), **array))

        ## make a task to loop over message felds
        # requiring 'n' as an input causes this field of the message to be copied
        # to a goal buffer slot of the same name.
        t = ActrMessageTask(task_name, inputs='n')
        t.p(actions="i 0", to_state="loop")
        t.p_if_then_else("<", "i", "n", to_state="get_field", else_to_state="cleanup")
        t.p_get_message_field("a", index_slot="i", output_slot="ai", to_state="announce")
        t.p_speak("Element ~A is ~A", slots=["i", "ai"], to_state="increment")
        t.p_increment("i", to_state="loop")

        # print(t)

        ## create a person who performs the task
        env=self.env
        class P(ActrMessagingPerson):
            ''' this is an actr person who collects what they say into self.speech '''

            def __init__(self):
                self.speech = []
                super().__init__("P9", mb, actr_tasks=t, message_driven=True, enable_actr_trace=False, simpy_env=env)

            def handle_actr_speech(self, s):
                if 'Element' in s:
                    self.speech.append(s)
                else:
                    # ActrMessagePerson won't work unless speech starting with reserved values is passed along.
                    super().handle_actr_speech(s)
        p=P()

        ## go
        self.env.run(self.env.now + 100)

        self.assertEqual(p.speech, ['Element 0 is 0',
             'Element 1 is 10',
             'Element 2 is 20',
             'Element 3 is 30',
             'Element 4 is 40'])

    def test_recursion(self):
        '''
        This exercises subtasks by using recursion.
        
        In particular it tests p_subtask - save_slots, rename_slots_before, rename_slots_after - 
          that enable calling a subtask that re-uses the same goal buffer slots 
        '''
        
        class Fibonacci(ActrPerson):
            
            def __init__(self, tests):
                self.results = dict()
                driver = ActrTask("driver", main_task=True)
                for x in tests:
                    driver.p_subtask(subtask="fib", actions="x {}".format(x), return_to_state="{}-print".format(x))
                    driver.p_subtask(subtask="print", return_to_state="{}-next".format(x), )

                p = ActrTask("print")
                p.p_speak("Comment: fibonacci(~A) = ~A", slots=["x", "y"])

                # parameters: x61646164
                
                # output: y = fibonacci(x)
#                 f = ActrTask("fib", log_inputs="x", log_outputs="y")
                f = ActrTask("fib")
                f.p_trace("inputs", slots=["x"], to_state="switch")
                f.p(conditions="x 0", from_state="switch", actions="y 0", to_state="cleanup", description="x0") # base case x=0
                f.p(conditions="x 1", from_state="switch", actions="y 1", to_state="cleanup", description="x1") # base case x=1

                f.p(conditions="> x 1", from_state="switch", to_state="x-1") # non-base case, we'll have to do some work.
                f.p_bind_slot("x-1", "- =x 1", to_state="fib-x-1")
                f.p_subtask(save_slots=["x"], rename_slots_before={"x-1":"x"}, subtask="fib", rename_slots_after={"y":"fib-x-1"}, return_to_state="x-2")
                f.p_bind_slot("x-2", "- =x 2", to_state="fib-x-2")
                f.p_subtask(save_slots=["x", "fib-x-1"], rename_slots_before={"x-2": "x"}, subtask="fib", rename_slots_after={"y":"fib-x-2"}, return_to_state="add")
                f.p_bind_slot("y", "+ =fib-x-1 =fib-x-2", to_state="cleanup")
                f.p_trace("outputs", slots=["y"])
                
#                 print(f)
                super().__init__("FIBBER", [driver, f, p])

            def handle_actr_speech(self, speech):
                m = re.search("fibonacci\((\d+)\) = (\d+)", speech)
                if m:
                    self.results[int(m.group(1))]=int(m.group(2))
                else:
                    print("NO MATCH: {}".format(speech))

        tests = {0:0, 1:1, 2:1, 3:2, 4:3, 5:5, 6:8, 7:13}
        f = Fibonacci(tests)

#         f.enable_actr_trace = True
#         f.enable_lisp_console_output(True)

        self.env.run(self.env.now+100) # first run just the sender, giving them time to send all the orders before any are taken out.  Otherwise the first one is done first, instead of priority order.
#         print(f.actr_eval("(printed-buffer-chunk 'goal)"))        
#         print(f.actr_eval("(printed-buffer-chunk 'imaginal)"))        
#         print(f.actr_eval("(printed-buffer-chunk 'retrieval)"))        

        self.assertEqual(tests, f.results)

class EchoPerson(ActrPerson):
    '''
        A simple actr model for testing.
    '''
    
    code = '''
      (install-device '("speech" "microphone"))
      (sgp :esc t :lf .05)
      (turn-off-act-r-output) ; disable echoing all the output to the lisp standard output, particularly "Stopped because time limit reached" every simulated second which really slows things down.  Can be counteracted by (echo-act-r-output) e.g. so you can interact at lisp console afterwards.  This does not prevent the trace from being sent to this client program and
      ;(echo-act-r-output) 
      (sgp :trace-detail low) ; even medium sends a constant barrage of TEMPORAL module messages (2 for every tick).  These can be filtered client-side but it's a lot to send and process and discard if we don't need it.
      (p echo
         =visual-location> message =msg
         ?vocal> state free
         ==>
         !bind! =msg-string (format nil "~A" =msg)
         +vocal> cmd speak string =msg-string
         )
         '''
    ''' this is the lisp code for the model, to be sent to define-model '''

    code2='''
        (p echo2
         =visual-location> message =msg
         ?vocal> state free
         ==>
         !bind! =msg-string (format nil "2 ~A" =msg)
         +vocal> cmd speak string =msg-string
         )
    '''
    ''' this is the code for an extra production.  It has the same preconditions as the 'echo' production in the model
        so we'll manipulate its utility using actr.spp("echo2", ":u", 1)
    '''
    
    def __str__(self):
        s = "Name: {}\n".format(self.name)
        s += "Things I said:\n"
        s += "\n".join(["  "+t for t in self.speech])
        return s
    
    def __init__(self, name, simpy_env, actr_code=None):
        super(EchoPerson, self).__init__(name, simpy_env=simpy_env, actr_code=actr_code)
        self.speech = []
        
    def handle_actr_speech(self, speech):
        self.speech.append(speech)
 
