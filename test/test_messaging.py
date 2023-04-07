'''
Created on Mar 24, 2020

@author: rgabbot
'''
import unittest
from cogtasks.messaging import MessageBroker, Message, State, AddressFilter
import simpy
from simpy.core import Environment
from random import shuffle

class TestMessage(unittest.TestCase):

    def test_access(self):

        m = Message(env=None, a='A', b='B')

        self.assertEqual('B', m.b)

        self.assertRaises(AttributeError, lambda: m.NOPE)

    def test_matches(self):
        m = Message(env=None, a='A', b='B')
        self.assertTrue(m.matches()) # any message matches the empty set
        self.assertTrue(m.matches(a='A'))

class TestMessaging(unittest.TestCase):


    def test_fifo(self):
        '''
        Absent any other factors, message_id's are assigned in ascending order, and messages are delivered in fifo order.
        '''        
        env = Environment()
        mb = MessageBroker(env)

        n = 5
        
        msglist = [ Message(env) for _ in range(n) ]
        
        # try this once to make sure the test will catch it.  (it does)
        #msglist[2], msglist[3] = msglist[3], msglist[2]
        
        [self.assertLess(msglist[i]._msg_id, msglist[i+1]._msg_id, "message ids are assigned in ascending order") for i in range(n-1)]
        
        # add the messages to MessageBroker out of order to make sure it will handle that correctly
        msglist[2], msglist[3] = msglist[3], msglist[2]        
#       
        for j in msglist:
            mb.put(j)
            # tried this once to make sure it will cause the test to fail by storing them out of order (it does) 
            # mb.items.append(j)
#         
        [self.assertLess(mb.items[i]._msg_id, mb.items[i+1]._msg_id, "message ids are assigned in ascending order") for i in range(n-1)]

        def consumer():
            prev_id = None

            while True:
                j = yield mb.get()
                if prev_id is not None:
                    self.assertGreater(j._msg_id, prev_id, "Messages are supposed to be returned in fifo order, i.e. lowest message_id first")
                prev_id = j._msg_id
                     
        env.process(consumer())
        env.run(1)
        self.assertEqual(mb.count_messages(state = State.ACCEPTED), n, "make sure the consumer checked them all")
        self.assertEqual(mb.count_messages(state = State.SUBMITTED), 0, "make sure the consumer checked them all")

    def test_get_message_by_id(self):
        env = Environment()
        mb = MessageBroker(env)
        ids = set()
        n=5
        for _ in range(n):
            j = Message(env)
            mb.put(j)
            ids.add(j._msg_id)
        self.assertEqual(len(ids), n)

        for msg_id in ids:
            j = mb.get_message_by_id(msg_id)
            self.assertEqual(j._msg_id, msg_id, "ensure get_message_id retrieves the correct message")

        # now make sure an invalid index raises an exception
        invalid_id = max(ids)+1            
        with self.assertRaises(ValueError):
            mb.get_message_by_id(invalid_id)
        
    def test_priority(self):
        '''
        Absent any other factors, messages are dispatched in priority order, lowest first.
        '''        
        env = Environment()
        mb = MessageBroker(env)

        prio = [*range(-5,5)]
        shuffle(prio)
        for i in prio:
            # converting i to a string to make sure they are compared as numbers.
            # as strings (i.e. in lexicographical ordering), -3 < -4    
            j = Message(env, priority = str(i))
            mb.put(j)

        def consumer():
            prev_pri = None
            while True:
                item = yield mb.get()
#                 print("At t={} I got {}".format(env.now, item))
                if prev_pri is not None:
                    self.assertGreater(float(item._msg_priority), float(prev_pri))
                prev_pri = item._msg_priority
                    
        env.process(consumer())
        env.run(1)

        self.assertEqual(mb.count_messages(state = State.ACCEPTED), len(prio), "make sure the consumer checked them all")
        self.assertEqual(mb.count_messages(state = State.SUBMITTED), 0, "make sure the consumer checked them all")
  
    def test_wait_to_be_closed(self):
        '''
        Tests sending a message, then waiting for it to be 'closed' and reading out the information added to it by the recipient.
        '''
        env = Environment()
        mb = MessageBroker(env)

        def sender():
            yield env.timeout(1)
            msg = Message(env, address="receiver", numerator=10, denominator=2)
            yield mb.put(msg) # this yield simply wants for the messagebroker to accept the message.
            result = yield msg # this yield waits for the recipient to call job.succeed()
            self.assertEqual(msg.ratio, 5)
            self.assertEqual(msg._msg_state, State.CLOSED)
            self.assertEqual(result, "MySuccessValue")

        def receiver():
            while True:
                job = yield mb.get(filter =  AddressFilter("receiver"))
                job.succeed("MySuccessValue", {"ratio": job.numerator / job.denominator})

        env.process(sender())              
        env.process(receiver())

        env.run(5)

#         print(mb)
        
    def test_message_modification(self):
        '''
        Tests modifying a message to ensure this makes it dispatch to a consumer who previously filtered it out.
        This test uses a "tech support" scenario where a "user" produces a message that is handled by tier 1 tech support.
        tier1 fails to resolve the issue and escalates it to tier2
        '''        
        env = Environment()
        mb = MessageBroker(env)

        def user():
            yield env.timeout(10)
            msg = Message(env, tier=1, sender="user", recipient=None)
#             
#             print("t={}: User submitting msg {}".format(env.now, msg))
            mb.put(msg)

            msg = yield mb.get(filter = lambda msg: msg.recipient == "user")
#             print("t={}: User got a message: {}".format(env.now, msg))
                        

        _self = self

        class Tech:
            def __init__(self, tier):
                self.tier=tier
            def do_jobs(self):
                while True:
#                     print("t={}: Tier {} waiting for a job".format(env.now, self.tier))
                    job = yield mb.get(filter = lambda job: job.tier == self.tier)
                    print("t={}: Tier {} working on job".format(env.now, self.tier, job))
                    yield env.timeout(5)
                    if self.tier == 1:
#                         print("t={}: Tier 1 failed to resolve the issue. resubmitting to tier 2".format(env.now))
                        job.tier = 2
                        mb.put(job)
                    else:
                        _self.assertEqual(self.tier, 2)
#                         print("t={}: Tier 2 resolved the issue".format(env.now))
                        job._msg_state = State.CLOSED
                        notification = Message(env, message="Repair is done")
                        notification.recipient = job.sender                        
                        mb.put(notification)
                        
        env.process(user())
        
        t1 = Tech(1)
        env.process(t1.do_jobs())

        t2 = Tech(2)
        env.process(t2.do_jobs())

        env.run(100)

#         print(mb)
  
    def test_multiple_preconditions(self):
        '''
        ensure completing a task with multiple other tasks waiting on it immediately frees all of them.
        '''        
        env = Environment()
        mb = MessageBroker(env)

        class MyMessage(Message):
            sequence_created = 0 # mark each job with the order in which it was created
            def __init__(self, env,  **kwargs):
                super().__init__(env, worker_id=None, sequence_accepted=None, sequence_created=MyMessage.sequence_created, **kwargs)
                MyMessage.sequence_created += 1

        # first create in a temporary list before adding, so we can add the dependencies to message 0 before adding.
        blockers = [MyMessage(env), MyMessage(env)]
        for b in blockers:
            mb.put(b)
        
        for _ in range(1,4):
            # assign priority of -sequence_created so jobs created later will be done first, to ensure jobs are done by priority and not just fifo.
            mb.put(MyMessage(env, preconditions=blockers, priority=-MyMessage.sequence_created))
        
        sequence_accepted = 0 # count up and record in the messages to capture the order in which they were dispatched by the message broker
        def worker(worker_id):
            nonlocal sequence_accepted
            while True:
                job = yield mb.get()
                job.sequence_accepted = sequence_accepted
                sequence_accepted += 1
                job.worker_id = worker_id
                yield env.timeout(1)
                job.succeed()
        
        for worker_id in range(0,5):
            env.process(worker(worker_id))
        env.run(5)

#         print(mb)

        # the first job was accepted immediately because it had no preconditions
        # the rest of the jobs were accepted immediately when the first job (which they depended on) was done.
        for j in mb.items:
            if j.sequence_created < len(blockers):
                self.assertFalse(hasattr(j, "preconditions"))
                self.assertEqual(j._msg_time_accepted, 0)
                self.assertEqual(j._msg_time_closed, 1)
            else:
                self.assertTrue(hasattr(j, "preconditions"))
                self.assertEqual(j._msg_time_accepted, 1)
                self.assertEqual(j._msg_time_closed, 2)


        # workers were given (i.e. accepted) jobs in the order they lined up for them by calling mb.get()
        for j in mb.items:
            self.assertEqual(j.worker_id, j.sequence_accepted)
        
        # jobs were dispatched (i.e. accepted) in priority order (not the order they were created in), 
        # except the first job which was issued out of priority order because it was the only one with no preconditions
        num_jobs = len(mb.items) 
        for j in mb.items:
            if j.sequence_accepted < len(blockers):
                self.assertFalse(hasattr(j, "preconditions"))
                self.assertEqual(0, j._msg_priority)
            else:
                self.assertTrue(hasattr(j, "preconditions"))
                self.assertEqual(j.sequence_accepted, num_jobs+1-j.sequence_created)
        
        # workers accepted jobs in the order the workers got in line for them - first-come, first-served

    def test_find_messages(self):
        env = Environment()
        mb = MessageBroker(env)
        mb.put(Message(env, a=1, b=1))
        mb.put(Message(env, a=1, b=2))
        mb.put(Message(env, a=2, b=2))

        self.assertEqual(2, len(mb.find_messages(a=1)))
        self.assertEqual(1, len(mb.find_messages(a=1,b=2)))


    def test_address(self):
        '''
          Make sure messages that are filtered out are not returned.
        '''        
        env = Environment()
        mb = MessageBroker(env)

        mb.put(Message(env, address = "jill")) # 1: to jill
        mb.put(Message(env, address = "jack")) # will NOT be received by jill
        mb.put(Message(env, address = None)) #  2: to anybody
        mb.put(Message(env)) # 3: also to anybody
        mb.put(Message(env, address = ["jack", "jill"])) # 4: to jack OR jill
        mb.put(Message(env, address = "chef")) # 5: to a chef
        mb.put(Message(env, address = ["plumber", "chef"])) # 6: to a plumber OR chef
        
        _self = self
        def jill():
            f = AddressFilter("jill") # string-to-string address match (both the filter and message specify a string)
            msg = yield mb.get(f) # 1
            _self.assertEqual(msg.address, "jill")
            
            msg = yield mb.get(f) # 2
            _self.assertEqual(msg.address, None)

            msg = yield mb.get(f) # 3
            _self.assertFalse(hasattr(msg, "address"))
            
            msg = yield mb.get(f) # 4: string-to-set address match
            _self.assertTrue("jack" in msg.address)
            _self.assertTrue("jill" in msg.address)
            
            f = AddressFilter(["jill", "chef"]) 
            msg = yield mb.get(f) # 5: set-to-string address match
            _self.assertEqual(msg.address, "chef")
        
            f = AddressFilter(["jill", "chef"]) # set-to-set address match
            msg = yield mb.get(f) # 5
            _self.assertTrue("plumber" in msg.address)
            _self.assertTrue("chef" in msg.address)
        
        env.process(jill())
        env.run(1)


    def test_fail(self):
        
        env = Environment()
        mb = MessageBroker(env)
        
        def worker():
            msg = yield mb.get()
            msg.fail(Exception("exception message"))
        env.process(worker())
        mb.put(Message(env))
        
        try:
            env.run(1)
            self.assertFalse(True) # won't get here because of exception
        except Exception as e:
            self.assertTrue("exception message" in str(e))
            # print("env.run raised exception: {}".format(e))


    def test_fail_to_client(self):
        
        env = Environment()
        mb = MessageBroker(env)

        def worker():
            msg = yield mb.get()
            yield env.timeout(5)
            msg.fail(Exception("my exception message"))

        client_got_exception = False
        def client():
            msg = Message(env)
            yield mb.put(msg)
            try:
                yield msg
                self.assertFalse(True) # won't get here becasue exception will be raised
            except Exception as ex:
                self.assertTrue("my exception" in str(ex))
                nonlocal client_got_exception
                client_got_exception = True

        env.process(client())
        env.process(worker())
        
        env.run(10)
        self.assertTrue(client_got_exception)
        
    def test_interruption(self):
        ''' Interrupt a Simpy process '''
        
        env = Environment()

        # in this test, we trace execution by adding "got here" messages to this array, and 'assert' its contents at the end.
        # This is instead of putting asserts all along the way, because asserts raise exceptions which simpy redirects to the env.run() 
        # call.  This becomes confusing when the test code is tracing what calls result in exceptions.
        
        sleeper_got_here = []
        def sleeper():
            try:
                yield(env.timeout(1000))
                sleeper_got_here.append("finished sleeping")
                
            except simpy.Interrupt as e:
                sleeper_got_here.append("sleeping interrupted with message: "+e.cause)

        sleeper_process = env.process(sleeper())

        alarm_got_here = []
        def alarm():
            yield(env.timeout(10))
            sleeper_process.interrupt("time's up!")
            alarm_got_here.append("first interrupt")

            # now we will (unnecessarily) interrupt the sleeper a couple more times.
            # this is to see what happens if redundant interrupts are ordered.

            # this first one does not raise an exception, and the message passed to the interrupt is not passed to the interrupted process.
            # Perhaps this is because the environment has not had a chance to run and process the previous interrupt.
            sleeper_process.interrupt("time's up 2!")
            alarm_got_here.append("second interrupt")

            # now let the environment run
            yield(env.timeout(1))

            # this time ordering the interrupt will cause a RuntimeError
            try:
                sleeper_process.interrupt("time's up 3!")
                alarm_got_here.append("third interrupt")
            except RuntimeError:
                alarm_got_here.append("error on third interrupt")

            
        env.process(alarm())
        
        env.run(20)
        
        self.assertEqual(sleeper_got_here, ["sleeping interrupted with message: time's up!"])

        self.assertEqual(alarm_got_here, ["first interrupt", "second interrupt", "error on third interrupt"])

        
    def test_interruption_propagation(self):
        ''' Interrupt a Simpy process and allow the Interrupt exception to propagate'''
        
        env = Environment()

        def sleeper():
            yield(env.timeout(1000))
            sleeper_got_here.append("finished sleeping")

        sleeper_process = env.process(sleeper())

        def alarm():
            yield(env.timeout(10))
            sleeper_process.interrupt("time's up!")
            
        env.process(alarm())

        got_exception = False
        try:
            env.run(20)
            self.assertFalse(True) # can't get here because the sleeper will raise an Interrupted exception
        except simpy.Interrupt as ex:
            got_exception = True
        self.assertTrue(got_exception)
        
        
    def test_interruption_catch_propagation(self):
        ''' Interrupt a Simpy process and catch the Interrupt in the process that causes it '''
        
        env = Environment()

        def sleeper():
            yield(env.timeout(1000))
            sleeper_got_here.append("finished sleeping")

        sleeper_process = env.process(sleeper())

        got_exception = False
        
        def alarm():
            yield(env.timeout(10))
            sleeper_process.interrupt("time's up!")
            try:
                yield sleeper_process
                self.assertFalse(True) # can't get here because the sleeper will raise an Interrupted exception
            except simpy.Interrupt as ex:
                self.assertEqual(env.now, 10)
                nonlocal got_exception
                got_exception = True
            
        env.process(alarm())

        env.run(20)

        self.assertTrue(got_exception)
        
    def test_send_sync__ok(self):
        '''
        A synchronous call should succeed if it takes less time than the timeout.
        '''
        env = Environment()
        mb = MessageBroker(env)
        task_time = 10
        timeout = task_time+100

        def recipient():
            m = yield mb.get()
            yield env.timeout(task_time)
            msg.succeed(True, {'result':'ok'})
        env.process(recipient())

        msg = Message(env, message='hi')

        def sender():
            m = yield from mb.send_sync(msg, timeout) # should not time out
            self.assertEqual(env.now, task_time)

        env.process(sender())
            
        env.run()

        # see the Timeout Note in the documentation for send_sync on why simulation time advances to the timeout
        # rather than just the task_time
        self.assertEqual(env.now, timeout)

        self.assertEqual(msg.result, 'ok') # this means the recipient got the message and modified it.

        print(msg)

    def test_send_sync__timeout(self):
        '''
        A synchronous call that times out
        '''
        env = Environment()
        mb = MessageBroker(env)
        task_time = 10
        timeout = task_time-5 # not long enough!   Will trigger a timeout as desired.

        def recipient():
            m = yield mb.get()
            yield env.timeout(task_time)
            msg.succeed(True, {'result':'ok'})
        env.process(recipient())

        msg = Message(env, message='hi')

        got_exception = False
        def sender():
            try:
                m = yield from mb.send_sync(msg, timeout)
                self.assertTrue(False) # should not be reached - exception should be raised
            except Exception as ex:
                nonlocal got_exception
                got_exception=True
                self.assertFalse(hasattr(msg, 'result')) # recipient has not yet set this
                self.assertTrue("timed out" in str(ex))
                #print("GOT EXCEPTION: {}".format(ex))
                self.assertEqual(env.now, timeout)

        env.process(sender())
            
        env.run()

        self.assertTrue(got_exception)
        
        self.assertEqual(env.now, task_time)

        self.assertEqual(msg.result, 'ok') # this means the recipient got the message and still processed it, even though the sender was no longer waiting for it.

        print(msg)

    def test_send_sync__error(self):
        '''
        A synchronous call from which the recipent returns an error
        '''
        env = Environment()
        mb = MessageBroker(env)
        task_time = 10
        timeout = task_time+5 # long enough.  Will not trigger a timoeut

        def recipient():
            m = yield mb.get()
            yield env.timeout(task_time)
            # calling msg.succeed with a string (rather than True) is how you flag an error in processing a message
            msg.succeed("There was some error!!!")
        env.process(recipient())

        msg = Message(env, message='hi')

        got_exception = False
        def sender():
            try:
                m = yield from mb.send_sync(msg, timeout)
                self.assertTrue(False) # should not be reached - exception should be raised
            except Exception as ex:
                nonlocal got_exception
                got_exception=True
                self.assertFalse(hasattr(msg, 'result')) # recipient has not yet set this
                self.assertTrue("There was some error" in str(ex))
                #print("GOT EXCEPTION: {}".format(ex))

        env.process(sender())
            
        env.run()

        self.assertTrue(got_exception)
        
        self.assertEqual(env.now, max(task_time, timeout))

        
if __name__ == "__main__":
    unittest.main()
