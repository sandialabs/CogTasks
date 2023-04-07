#!/usr/bin/python3

import actr
import sys
import re
import traceback

def actr_eval(s):
    '''
    Send a string to lisp code (which may include multiple expressions) to be evaluated.
    This won't work until after actr-person.lisp is read into lisp because it uses read-eval-string which is defined there.
    '''
    y = actr.current_connection.evaluate_single("read-eval-string", s)
    # functions without return values return None
    # This assert catches define-p failures which is how compile errors for lisp code are indicated.
    # This is important because otherwise it is easy to overlook invalid actr code and wonder why it didn't fire.
    # On the other hand it's conceivable some function may return False not because it failed but because that's a valid response,
    # so this might need to be reconsidered.
    assert(y is not False)
    return y

class ActrTask:
    '''
    ActrTask assists in writing act-r productions that follow the Tasks convention 
    which is documented in ACTR Subtasks.docx and implemented in actr-tasks.lisp
    
    This is essentally just a macro; it isn't required for writing Tasks, but reduces repetition (and therefore chances for things to not line up)
    '''
    
    def __init__(self, task_name, main_task=False, inputs=None, outputs=[]):
        '''
        Set main_task to True if this is the entry point for the actr.  I.e. this task will not be called from another task, but should be started when the program runs.
          If main_task is True, then if a start production is generated (i.e. from_state=="start"), 
          it will be prepended with a production to check if the goal buffer is empty and if so set this as the current task and set the task_state to start
          
        inputs: if specified, is a list of goal buffer slots that will be added to the trace message produced by p_trace_inputs.
          In addition, any inputs that are not specified as outputs will be deleted by the cleanup state.
        
        outputs: if specified, names goal buffer slots that will be added to the trace message produced by p_trace_outputs.
        
        '''
        self.task_name = task_name
        self.prev_state = "start"        
        self.main_task = main_task
        
        self.inputs = inputs
        self.outputs = outputs
        
        self._cleanup_slots = set()
        
        if inputs:
            for i in inputs:
                if outputs is None or i not in outputs:
                    self._add_to_cleanup(i)
        
        self.results = ""
        ''' this string accumulates all the return values, and the __str__ operator returns them. '''
        
        self.subsymbolic = None
        '''
        Whether this task uses subsymbolic computation.  By default it is unspecified (None).
        If an productions created with p() specify a utility value, it will be set True.
        '''

    def p(self, from_state=None, to_state=None, conditions=None, actions=None, description=None, utility=None, cleanup=None):
        '''
        This is the basic function of this class - it writes a production.
        
        returns a string for a production that fires if this is the current task and its task-state is from_state,
          which will transition the task-state to to_state.
          
        this is named after the ACT-R command "p" (or "define-p")
        
        additional 'conditions' and 'actions' can be specified in the corresponding parameters. When specifying values
          for these parameters, do not specify the =goal> buffer, any statements before the first buffer specification apply to the goal buffer.

        If the from_state is None it defaults to 'start'
        If to_state is None it defaults to the from_state for the previous call.  
          This allows creating a chain of productions simply by specifying to_state each time.  See test_actr_task in test_actr_person.
          
        'description' will be added to the name of the production.  
        This doesn't need to be specified unless different productions can fire from the same task state, i.e. based on additional conditions.
        This should not be a lengthy description and should be an identifier; it will be added to the name of the production.
        
        Utility optionally specifies an act-r 'utility' value for this production.
        For this to function the global parameter :esc (enable subsymbolic computation) must be true.
        
        Cleanup is a slot name, or list of slot names, to be set to 'nil' in the 'cleanup' production 
        Its use is to clear out slots that are created by this task, but are not return values.
        Multiple calls to 'p' specifying a value for cleanup accrue slot names in self._cleanup_slots.
        It is not an error to add the same slot name repeatedly.
        '''
        
        self._add_to_cleanup(cleanup)
        
        if from_state is None:
            from_state = self.prev_state
        
        if to_state is None:
            to_state = "done"
        
        if actions is None:
            actions = ""
        
        if conditions is None:
            conditions = ""
        
        if description is None:
            description = ""
        else:
            description = "--" + description
        
        s = ""
        
        if from_state.lower() == "start" and self.main_task:
            s = '''
(p ''' + self.task_name + "--main"+description+'''
  ?goal>
    buffer empty
  ==>
  +goal>
    task ''' + self.task_name + '''
    task-state start)'''
            self.main_task = False # generate this only once.
            
        production_name =  self.task_name + '--' + from_state + description
            
        s += '''
(p ''' + production_name + '''
  =goal>
    task '''+self.task_name+'''
    task-state ''' + from_state + " " + conditions + '''
  ==>
  =goal>
    task-state ''' + to_state + " " + actions + ")"
 
        if utility is not None:
            self.subsymbolic = True
            s += '''
(spp {} :u {})'''.format(production_name, utility)
        
        self.prev_state = to_state
        
        self.results += s
        
        return s

    def p_subtask(self, from_state=None, save_slots=None, rename_slots_before=None, subtask=None, rename_slots_after=None, return_to_state=None, 
                  conditions=None, actions=None, description=None, utility=None, cleanup=None):
        '''
            Add a production to call a subtask.
            
            In the simplest case (if there are no parameters or return values or slots that would be clobbered),
              only the 'subtask' parameter is required
            
            The parameters represent a sequence of actions to take:
            1) save_slots: a list of goal buffer slots to be 'saved' from being clobbered by the subtask.
               these slots are copied to the imaginal chunk that goes into declarative memory,
               thus saving the state of this task before calling the subtask
            2) rename_slots_before: a dict of slot renamings to be performed before calling the subtask. 
               The normal use of this is to put values in the slots where the subtask expects to find them.
               E.g. if the subtask expects to find its arguments in slots a and b, but the values are currently in x and y, use {"x":"a", "y":"b"}
            3) subtask: this is the subtask to be called (either a string, or an ActrTask instance in which case its task_name is used.)
               Note it will only fire if whatever conditions it specifies are met.
            4) rename_slots_after: a dict of slot renamings to be performed AFTER calling the subtask.
               The normal use of this is to put return values from the subtask into slots that make sense for the caller.
               For example if the subtask stores its result in slot "y", to have it moved to a slot called "weight" use {"y":"weight"}
            5) [save_slots]: these slots are restored, by retrieving the chunk saved from the imaginal buffer into the retrieval buffer,
               and copying the specified slots back to the goal buffer.
            6) return_to_state: the calling task resumes in this task-state after the subtask is done.
            
        '''
        ## condition
        if conditions is None:
            conditions = ""
        # goal buffer slots to collect into variables, for either save-slots or rename-slots-before.
        varnames = set()
        if rename_slots_before:
            assert(isinstance(rename_slots_before, dict))
            varnames.update(rename_slots_before)
        if save_slots:
            assert(isinstance(save_slots, list))
            varnames.update(save_slots)
        if len(varnames) > 0:
            conditions += "\n    "+"\n    ".join(["{} ={}".format(x,x) for x in varnames])
        conditions += "\n  ?imaginal> state free" # calling a subtask uses the imaginal buffer so can only be done after the imaginal buffer frees up.
        
        ## actions
        if actions is None:
            actions = ""
            
        assert(subtask is not None)
        if isinstance(subtask, ActrTask):
            subtask = subtask.task_name
            
        actions += "\n    subtask "+subtask # specify subtask to call
        # any slots that are the source for a rename, but not a destination, are nil'ed out
        # dont_erase can specify addtional slots not to nil out - this is used by rename_slots_after
        # to avoid nulling out slots that are also set by save_slots
        def rename_slots(a, dont_erase=[]):
            # first, nullify slots that are sources and not destinations.
            result = ""
            if a is None or len(a)==0:
                return result
            ys = set(list(a.values())+dont_erase)
            nils = set([x for x in a if x not in ys])
            if len(nils) > 0:
                result += "\n    "+"\n    ".join(["{} nil".format(x) for x in nils])
            # now, assign destinations.
            result += " \n    "+"\n    ".join(["{} ={}".format(y,x) for x,y in a.items()])
            return result
            
        actions += rename_slots(rename_slots_before)

        # part of the 'action' is storing the state of the calling task in the imaginal buffer
        if return_to_state is None:
            return_to_state = "done"
        cleanup_state = "cleanup-from-"+subtask+"-before-"+return_to_state
        actions += "\n  +imaginal> task-state " + cleanup_state # remember where we want to resume the calling task.
        if save_slots is not None:
            actions += "\n    "+"\n    ".join(["{} ={}".format(x,x) for x in save_slots])
        
        s = self.p(from_state=from_state, to_state="subtask", conditions=conditions, actions=actions, description=description, utility=utility, cleanup=cleanup)
        
        #### write the cleanup production
        conditions = ""
        # rename_slots_before and save_slots both took their values from the goal buffer,
        # but when restoring, save_slots gets its values from the retrieval buffer.  
        # so the same name could be present in both rename_slots_after and save_slots, and refer to different things.
        # For example the subtask return value might be "y", but the calling task wants it called "subtask-y" and have its own "y" slot restored.
        # So they need to be stored in variables with different names.
        
        # get variables from goal buffer for rename_slots_after
        if rename_slots_after is not None and len(rename_slots_after) > 0:
            conditions += "\n    "+" ".join(["{} ={}".format(x,x) for x,y in rename_slots_after.items()])
        # get variables from retrieval buffer for save_slots
        if save_slots is not None and len(save_slots) > 0:
            restore_saved = "\n    " +"\n    ".join(["{} ={}-saved".format(x,x) for x in save_slots])
            conditions += "\n  =retrieval> " + restore_saved
        
        actions = ""
        actions += rename_slots(rename_slots_after, dont_erase=save_slots if save_slots else [])
        if save_slots is not None and len(save_slots) > 0:
            actions += restore_saved
            actions += "\n  =retrieval>" # since we accessed it in the conditions, we must reference it in the action or it will be harvested (disappear)
        
        s += self.p(from_state=cleanup_state, to_state=return_to_state,
                    conditions=conditions,
                    actions=actions,
                    description=description,
                    utility=utility)
        
        self.prev_state = return_to_state
        
        return s

    def p_bind_slot(self, output_slot, variable_form, input_slots=None, from_state=None, to_state=None, conditions=None, actions=None, description=None, utility=None):
        '''
        Make a production to 'bind' output_slot in the goal buffer to some lisp variable_form
        e.g. p_bind_slot("y", "* =x =x") computes x^2 and stores it in y (assuming there exists a slot named x in the goal buffer).
        
        Why the = signs?  In act-r, !bind! cannot operate on slots directly, only variables, so this works 
        by creating a variable for each input_slot, and the output_slot.
        Thus in the variable_form, you must use an '=' before each slot name.
        
        input_slots: if specified, lists the slots to be bound to variables.
           If None, this code assumes each '=' followed by alphanumeric characters (plus  '_' or '-') is a slot that should be bound to a variable.
             (This is not robust and doesn't catch all legal identifiers - in that case specify input_slots directly or use nicer slot names)
           If the empty list, only the output_slot is created.   
        '''
        if conditions is None:
            conditions = ""
        if input_slots is None:
            input_slots = set(s.group(1) for s in re.finditer('=([\w-]+)', variable_form))
        if len(input_slots) > 0:
            conditions += "\n    ".join(["{} ={}".format(x,x) for x in input_slots])
        conditions += "\n    !bind! ={} ({})".format(output_slot, variable_form)
        
        if actions is None:
            actions = ""
        store_slot = "\n    {} ={} ".format(output_slot, output_slot)

        return self.p(from_state=from_state, to_state=to_state, conditions=conditions, actions=store_slot+actions, description=description, utility=utility)

    def p_speak(self, output, slots=[], from_state=None, to_state=None, conditions=None, actions=None, description=None):
        '''
        Create a production to use the ACT-R speech device to "say" the specified output.
        (Note this is NOT the same as sending a message through the message broker)
        Slots can specify a list of slots in the goal buffer. This production will only fire if they are all present.
        Slots can also include the special name "mp-time" which is available automatically (without being in the goal buffer) and provides the current act-r time from the (mp-time) lisp command.  
          The output must contain a matching number of listp format-specifiers, e.g. ~A
        If this production does not seem to be firing when it should, note that it is conditioned on "?vocal> state free"
          in other words, ACT-R imposes a limitation on how quickly a person can speak, so speech productions
          (especially one after another) cause the model to take extra time to execute.   
        '''

        if conditions == None:
            conditions = ""
        else:
            conditions += " "

        if isinstance(slots, str):
            slots = [slots]

        conditions += " ".join(["{} ={}".format(s,s) for s in slots if s != "mp-time"] )
        conditions += "\n ?vocal> state free"
        
        if actions == None:
            actions = ""
        else:
            actions += " "
            
        actions += '!bind! =mp-time (mp-time) !bind! =msg-string (format nil "'+output+'" '+" ".join(["="+s for s in slots])+')'
        actions += "\n +vocal> cmd speak string =msg-string"

        return self.p(from_state=from_state, to_state=to_state, conditions=conditions, actions=actions, description=description)

    def p_trace(self, message, slots=[], from_state=None, to_state=None, conditions=None, actions=None, description=None):
        '''
         Writes a message to the logfile.
         The message may contain formatting codes ~A to be matched by an equal number of slots (in the goal buffer).
        '''
        if actions is None:
            actions = ""
        # eg.g. "!eval! (task-trace 'inputs 'x 'y)"
        actions += '\n    !eval! (task-trace "{}"{})'.format(message, "".join([" '"+s for s in slots]))  

        y = self.p(from_state=from_state, to_state=to_state, conditions=conditions, actions=actions, description=description)
        return y

    def p_trace_inputs(self, slots=None, from_state=None, to_state=None, conditions=None, actions=None, description=None):
        if slots is None:
            slots = self.inputs
        self.p_trace("inputs{}".format("".join([" {} ~A".format(s) for s in slots])), slots=slots, from_state=from_state, to_state=to_state, conditions=conditions, actions=actions, description=description)
        
    def p_trace_outputs(self, slots=None, from_state=None, to_state=None, conditions=None, actions=None, description=None):
        if slots is None:
            slots = self.outputs
        self.p_trace("outputs{}".format("".join([" {} ~A".format(s) for s in slots])), slots=slots, from_state=from_state, to_state=to_state, conditions=conditions, actions=actions, description=description)
        
    def p_wait(self, seconds, from_state=None, to_state=None, conditions=None, actions=None, description=None, utility=None):
        '''
        Does nothing for approximately the specified number of seconds (in simulation time).
        This uses the act-r temporal module, so it is imprecise by design, and will interfere with anything else the temporal module might have been doing!
        '''
        if from_state is None:
            from_state = self.prev_state
        
        if to_state is None:
            to_state = "done"

        waiting_state = "waiting-between-{}-and-{}{}".format(from_state, to_state, "-"+description if description else "")
        
        if actions is None:
            actions = ""
        actions += " +temporal> ticks 0"

        s = ""
        s += self.p_bind_slot("ticks-to-wait", "ticks-for-seconds {}".format(seconds), from_state=from_state,
                              to_state=waiting_state, conditions=conditions, actions=actions, description=description, utility=utility)
        
        conditions = "ticks-to-wait =ticks-to-wait =temporal>   >= ticks =ticks-to-wait".format(seconds) 
        s += self.p(from_state=waiting_state, to_state=to_state, conditions=conditions, actions="ticks-to-wait nil", description=description)
        
        return s

    def p_if_then_else(self, cmp=None, slot_a=None, slot_b=None, var_b=None, value_b=None, from_state=None, to_state=None, else_to_state=None):
        '''
        Applies the comparison operator cmp which must be one of = < > <= >= between the values in slot_a and slot/variable/value_b in the goal buffer chunk.
        If cmp is true, task_state is set to to_state.  If false, task_state is set to else_to_state

        "b" (the right-hand side of the comparison) can be specified as a goal buffer slot, an act-r variable, or a value (e.g. a number, or unquoted string) 
        using slot_b, var_b, or value_b one and only one of these should be specified.
        
        After calling this, prev_state is to_state.
        '''

        complement = {"=":"-",
                      "-": "=",
                      "<":">=",
                      ">":"<=",
                      "<=":">",
                      ">=":"<"}

        if cmp not in complement:
            raise ValueError("p_if_then_else: cmp must be one of {} but got {}".format(" ".join(complement), cmp))

        if slot_a is None or sum(1 for b in [slot_b, var_b, value_b] if b is not None) != 1:
            raise ValueError("p_if_less_than: must specify slot_a, and exactly one of slot_b, var_b, or value_b")

        if from_state is None:
            from_state = self.prev_state
        
        conditions = ""

        # in act-r, the right-hand side of a slot-test must be either a variable or a value.
        # b will represent either slot_b, var_b, or value_b (whichever was specified)
        # in the case of slot_b, b will be a variable into which the slot is copied.
        b = None
        
        if slot_b: # if b was specified as a goal buffer slot...
            # since slot_b specifies a slot, we must copy it to a variable to do the comparison.
            b = "={}".format(slot_b)
            conditions += "{} {} ".format(slot_b, b) # create var_b to hold slot_b
        
        elif var_b:
            if not var_b.startswith("="):
                raise ValueError("p_if_then_else: parameter var_b must specify a variable but {} does not start with =".format(var_b))
            b = var_b[1:]
        
        elif value_b is not None:
            b = value_b
                
        else:
            assert(False) # shouldn't happen since we tested that only 1 was specified.

        conditions += "{} " + "{} {}".format(slot_a, b) # a format string lacking only the comparison operator, e.g. "{} x =y"

        s = self.p(from_state=from_state, conditions = conditions.format(complement[cmp]), to_state=else_to_state, description="{}_{}_F".format(slot_a, slot_b))
        s += self.p(from_state=from_state, conditions = conditions.format(cmp), to_state=to_state, description="{}_{}_T".format(slot_a,slot_b)) # this one is done second so prev_state is to_state.
        
        return s

    def p_increment(self, slot, from_state=None, to_state=None, description=None):
        ''' add 1 to the value in the specified slot '''

        # the main chore is moving the slot into a variable and back out since !bind! operates only on variables.
        conditions = "{} ={}".format(slot,slot)
        conditions += " !bind! ={}-plus-1 (+ 1 ={})".format(slot, slot)
        actions = "{} ={}-plus-1".format(slot,slot)
        
        return self.p(conditions=conditions, actions=actions, from_state=from_state, to_state=to_state, description=description)
    
    def p_once(self, flag, from_state=None, to_state=None, conditions=None, actions=None, description=None, utility=None, cleanup=None):
        '''
        Creates a production that will only fire once during the task.
        This is done by setting a flag (which is a goal buffer slot) to the value T when the production fires,
        and firing only if the flag has not been set.
        The flag is added to the cleanup list.
        '''
        
        if conditions is None:
            conditions = ""
        conditions += " {} nil".format(flag) # only fire if the flag has not already been set.
        
        if actions is None:
            actions = ""
        actions += " {} T".format(flag) # if it does fire, set the flag so it won't fire again.
        
        self._add_to_cleanup(flag)
        
        self.p(from_state=from_state, to_state=to_state, conditions=conditions, actions=actions, description=description, utility=utility, cleanup=cleanup)
    
    def p_cleanup(self, from_state="cleanup", to_state="done", conditions=None, actions=None, description=None, utility=None, cleanup=None):
        '''
        Creates a production that transitions from "cleanup" to "done",
        and deletes (sets to nil) any goal buffer slots specified as 'cleanup' arguments
        p_cleanup should be called once after all the other productions have been created, otherwise it won't know about slots created subsequently that should be cleaned up. 
        '''
        self._add_to_cleanup(cleanup)
        if actions is None:
            actions = ""
        actions += " "+" ".join("{} nil".format(slot) for slot in self._cleanup_slots)
        self.p(from_state=from_state, to_state=to_state, conditions=conditions, actions=actions, description=description, utility=utility)

    def _add_to_cleanup(self, slots):
        '''
        add a slot or array of slots to self.slots, which will be set to nil by p_cleanup.
        Any slots specified as outputs (i.e. found in self.outputs, as specified at construction) will be silently ignored - i.e. not cleaned up.
        '''
        if slots is None or len(slots)==0:
            return
        
        if isinstance(slots, str):
            if self.outputs is None or slots not in self.outputs:
                self._cleanup_slots.add(slots)
       
        else:
            for s in slots:
                self._add_to_cleanup(s)
            
    def __str__(self):
        return self.results

def check_actr_tasks(actr_tasks):
    '''
    actr_tasks: is null, or an instance of ActrTask, or iterable of instances of ActrTask.
    returns: the ActrTask instance(s) in a list, which is empty if actr_tasks was null or an empty list.
    '''
    assert not isinstance(actr_tasks, str) # this would fail the following assertion anyways but this makes the problem more obvious.
    
    if actr_tasks is None:
        actr_tasks = []
    
    try:
        for t in actr_tasks:
            assert isinstance(t, ActrTask)
    except:
        assert isinstance(actr_tasks, ActrTask)
        actr_tasks = [actr_tasks] # now we know it's a list of ActrTask
        
    return actr_tasks



class ActrPerson:
    actr_person_registry = {}
    '''
    actr.py does not provide a way to map ACT-R model names to python object instances (e.g. instance of Person)
    This class addresses this with the actr_person_registry which maps model name to python instance.

    NOTE!  actr.py does not correctly handle model names containg lower-case letters.  set_current_model mangles the case.
    So you cannot have ActrPerson instances whose names differ only in upper/lower-case.
    '''

    _simpy_actr_running = False

    code = '''
    (install-device '("speech" "microphone"))
    (sgp :trace-detail low) ; even medium sends a constant barrage of TEMPORAL module messages (2 for every tick).  These can be filtered client-side but it's a lot to send and process and discard if we don't need it.
    
    '''
    ''' this is boilerplate code sent to all actr_person instances'''

    def __init__(self, name, actr_tasks=None, actr_code=None, enable_actr_trace=False, simpy_env=None, task_logger=None):
        '''
            Creates an ACTR model of the specified name, and makes it the current model so subclasses can add productions etc.
            Also loads actr-tasks, and installs the 'microphone' device so that speech will make it back to python.
            
            actr_tasks: if specified, is an ActrTask or iterable of them, whose code will be added to the model.

            actr_code: if specified, lisp code to be evaluated within the call to define-model

            simpy_env should be specified only if this actr is in a SimPy simulation.
              If specified, a SimPy process will be created to run actr in synchrony with SimPy.
              If multiple ActrPerson instances are created, the same SimPy environment must be passed to all of them
              (or equivalently only passed to one of them) because multiple SimPy environments and/or act-r metaprocesses are not supported.    

        '''
        if name != name.upper():
            raise ValueError('ActrPerson name must be all caps (see comments on ActrPerson.actr_string in actr_person.py)')
        
        self.name = name
        self.actr_person_registry[self.actr_name()] = self
        self.visicon_id = None

        if actr_code is None:
            actr_code=""
        
        if actr_tasks:
            actr_tasks = check_actr_tasks(actr_tasks)
            
            for t in actr_tasks:
                actr_code += str(t)
            
            if any([t.subsymbolic for t in actr_tasks]):
                actr_code += "(sgp :esc t)" # enable subsymbolic computations, such as utility scores.

                actr_code += "(sgp :er t)"  # enable-randomness true: if true, productions tied for utility will be chosen randomly.

                # this adds noise to production utilities so the behavior is more random.
                # a very small value is sufficient to make ties broken randomly while generally respecting actual differences in utility.
                actr_code += "(sgp :egs .0001)"

                print("{}: enabling subsymbolic computations".format(name))
        
        actr_eval("(define-model {} {} {})".format(ActrPerson.actr_string(self.name), ActrPerson.code, actr_code))
        self.set_current_model()
        actr.load_act_r_code("actr-tasks.lisp")

        self.enable_lisp_console_output(False)

        self.current_tasks = [] # this is the call stack of tasks currently in progress (started but not yet done)
        self.task_log = [] # this is history of all subtasks of the current toplevel task including already-finished ones, in order they were started.

        self.enable_actr_trace = enable_actr_trace

        if simpy_env:
            self.simpy_env = simpy_env
            self._run_simpy_actr_once(simpy_env)
            
        # todo: allow setting this, to get task logging working 
        self.logger = task_logger

    '''
    All the instances of ActrPerson are hosted in one instance of actr, and here we set up a simpy process to run actr 
    in corresponding timesteps.
    '''
    def _run_simpy_actr_once(self, simpy_env):
        if ActrPerson._simpy_actr_running:  # this is what makes it run only once.
            return
        ActrPerson._simpy_actr_running = True
        
        # timestep determines how closely actr and simpy are synchronized, and therefore limits the precision of simpy timestamps applied to actr execution.
        # a smaller timestep is better but results in a lot of overhead, running act-r for fractions of a second at a time.
        timestep = 1
        _self = self
        def simpy_actr():
            while(True):
#                 print("Running ACTR: {}".format(timestep), file=sys.stderr)
#                actr.run_full_time(timestep) # doesn't work because time can suddenly jump past the desired time if there are no actr events.
                actr.run_until_time(timestep+simpy_env.now) # note: the actr run must be called before yield, otherwise if you run to a specified time, simpy has had one extra turn.
                yield simpy_env.timeout(timestep)
        simpy_env.process(simpy_actr())

    def delete_model(self):
        actr_eval("(delete-model {})".format(self.name))

    @classmethod
    def dispatch_output(cls, name, output, arg):
        ''' 
        process "output" from act-r output devices, e.g. microphone, keyboard.
        Note this is separate from the 'trace' console output, which is handled by actr_trace
        '''
#         print("dispatch_output: {} {} {} {}".format(cls, name, output, arg))
        
        try:
            person = cls.actr_person_registry[name]
            if output == 'output-key':
                person.handle_actr_keypress(arg)
            elif output == 'output-speech':
                person.handle_actr_speech(arg)
            else:
                raise Exception("ActrPerson.dispatch_output: unknown output: {}".format(output))
        except Exception as ex:
            print("Error dispatching output \"{}\" to ActrPerson \"{}\"".format(output, name))
            traceback.print_exc()
            raise

    @classmethod
    def get_person_by_name(cls, name):
        '''
        If the name string provide starts with the name of any of the ActrPerson instances, return it.
        Else raise KeyError
        '''

        if name == "" and len(cls.actr_person_registry)==1:
            name = list(cls.actr_person_registry.keys())[0]
        
        for name0, person0 in cls.actr_person_registry.items():
            if name.startswith(name0) or name.startswith(person0.actr_name()):
                return person0
        print("ERROR: No such actr person: {}".format(name), file=sys.stderr)
        raise KeyError("No such actr person: {}".format(name))
        
    def set_current_model(self):
        '''
        Set myself as the 'current model' which is necessary before most actr commands.
        '''
        actr.set_current_model(self.actr_name())

    def actr_name(self):
        return ActrPerson.actr_string(self.name)

    @staticmethod
    def actr_string(s):
        '''
            In the python code there are no restrictions on the characters to use in the name of the person.
            But the name links this python instance to the corresponding model in ACTR, so the name must
            be lisp-compliant.

            The earlier approach of this code was to convert the string to one that was lisp-compliant,
            but having different names for things in the python vs. lisp inevitably caused confusion.

            In theory quoting could be used in LISP to preserve the name, e.g. |CamelCase|
            however, attempting this immediately failed in actr.py since it keeps a registry of models
            and the vertical-bar quoting was stored in the python-side name of the mapping.
            It seems impractical to pursue this and better to allow only symbol names that won't
            be mangled by Lisp.
        '''

        return s

        # if isinstance(s, str):
        #     if s.upper() != s:
        #         raise ValueError(f"The string {s} is not uppercase, which causes problems with lisp")
        #     if ' ' in s:
        #         raise ValueError(f"The string {s} contains a space, which causes problems with lisp")
        #
        # return s


    def actr_eval(self, cmd):
        return actr_eval("(with-model " + self.name + " " + cmd+")")

    def get_goal_slot(self, slot):
        ''' get the value of a slot in the goal buffer chunk '''
        return self.actr_eval("(chunk-slot-value-fct (buffer-read 'goal) '{})".format(slot))
    
    def cleanup(self, time):
        self.set_current_model()
        # if logging to a file, it will not be flushed until the model is reset or logging is set to somewhere else.
        # this sets it to the 'model trace' which ends up in stdout.
        actr.set_parameter_value(":v", "t")
        self._write_task_log(time)
    
    def enable_lisp_console_output(self, enable):
        '''
        enable/disable printing all the output to the lisp standard output, 
        e.g. "Stopped because time limit reached" every timestep (which really slows things down.)
        This does not prevent the trace from being sent to this client program; it only effects output on the lisp console.        
        '''
        
        self.set_current_model()
        if enable:
            actr_eval('(echo-act-r-output)')
        else:
            actr_eval('(turn-off-act-r-output)')
        
    def actr_trace(self, actr_time, actr_module, actr_cmd, actr_args):
        '''
          handle act-r output that reports conflict resolution, productions firing, and so on.         
            (except those ignored by dispatch_actr_trace, below)
          The default here is just to print the trace if an attribute enable_actr_trace is True.  By default it is not set.
          Derived class may do specialized processing (such as logging).
          note, this does NOT impact "output" from simulated devices, e.g. act-r microphone or keyboard,
            which is what should be used by the agent to interact with the external world (not by monitoring trace messages here)

        '''
        
        if self.enable_actr_trace:
            print("{:.3f}\t{}:\t{}\t{}\t{}".format(actr_time, self.name, actr_module, actr_cmd, actr_args))

    def actr_trace_task(self, time, task, depth, message, **more):
        '''
          handle act-r ouptut reporting the execution of tasks (aka subtasks).
          This output comes from act-r but is generated by code in the function task-trace in actr-tasks.lisp (i.e. our extension to actr for tasks)
          
          time: this is the actr time at which the message was generated, which may no longer be the current time.
          task: name of the task being reported on
          depth: this captures the task/subtask structure among the calls.  If a task invokes a subtask, the depth of the subtask is greater by 1.
          state: either 'start' or 'end'
        '''

        # print("actr_trace_task(t={}, task={}, depth={}, message={}, {})".format(time, task, depth, message, more))

        # the start and end of tasks are reported separately.
        # that means if a task calls a subtask, there are two starts, then two-ends.
        # so to output them in order, we need to maintain the call stack
        # (RBB can handle events created out of order just fine, but it makes it harder to look through the logfile manually)
        
        class Task:
            def __init__(self, person, start, task_name, depth):
                self.person = person
                self.start = start
                self.end = None # to be set when the task ends.
                self.task_name = task_name
                self.depth = depth
                
            def __str__(self):
                return "task={} start={} end={} depth={}".format(self.task_name, self.start, self.end, self.depth)
         
        if message == "start":
            t = Task(self.name, time, task, depth)
            self.task_log.append(t)
            self.current_tasks.append(t)
            assert depth == len(self.current_tasks), "depth={}, current length {}".format(depth, len(self.current_tasks))
        elif message == "end":
            assert depth == len(self.current_tasks)
            t = self.current_tasks[-1]
            assert task == t.task_name 
            t.end = time
            self.current_tasks.pop()

            # until the toplevel task finishes, we don't know when it will finish so we can't write it out yet.
            # but if we write subtasks as they finish, they will be written out of order, because the toplevel task started before they did.
            if len(self.current_tasks) == 0:
                self._write_task_log(time)
        else:
            assert depth == len(self.current_tasks)
            t = self.current_tasks[-1]
            assert task == t.task_name
            setattr(t, message, dict(**more))

    def _write_task_log(self, time):
        '''
        Write out all the tasks currently in the task log, and truncate it.
        Any unfinished tasks will have an assumed end time of now.
        '''
        
#         assert self.logger
        
        # todo: make a named constructor parameter to set this.
        if self.logger is None:
            return
        
#         print("writing {} tasks".format(len(self.task_log)))
        for t in self.task_log:
            end = t.end if t.end is not None else time # Any unfinished tasks will have an assumed end time of now.
            tags = []
            for k,v in t.__dict__.items(): # each of the attributes in this task record is either a dict, else treat as scalar.
                if k == "start" or k == "end":
                    continue # these are treated specially
                try:
                    tags += [(k, ",".join([v2 for k2,v2 in v.items()]))]
                except:
                    tags += [(k, v)]
            self.logger.log(tags, t.start, end)
        self.task_log = []        

    def handle_actr_speech(self, speech):
        '''
             This default implementation doesn't know how to do anything but print and otherwise ignore speech starting with "Comment: "
        '''
        if speech.startswith("Comment: "):
            print(speech)
        else:
            raise Exception("ActrMessagingPerson.handle_actr_speech received a message it does not understand")
        
    @classmethod
    def cleanup_everybody(cls, time):
        for p in cls.actr_person_registry.values():
            p.cleanup(time)
#         actr.stop()
#         print("Invoked actr.stop", file=sys.stderr)

    @classmethod
    def dispatch_actr_trace(cls, trace_type, msg):

        critical = "|".join(["end of warnings for undefined production",
                    # clobbering one production with another:
                    "Production .* already exists and it is being redefined",
                    "already the name of a model in the current meta-process.  Cannot be redefined.",
                    "Visicon feature.*did not contain a valid feature and was not created."])

        ignore = "|".join([
            # could declare all these in the actr code to avoid these
            "Creating chunk .* with no slots",
            "Production .* uses previously undefined slots",
            "Extending chunks with slot named .* because of chunk definition",
            # these fire for every subtask
            "SET-BUFFER-CHUNK IMAGINAL",
            "PRODUCTION-FIRED START-SUBTASK",
            "PRODUCTION-FIRED PUSH-IMAGINAL-TO-NEW-LIST",
            "PRODUCTION-FIRED PUSH-IMAGINAL-TO-LIST",
            "PRODUCTION-FIRED START-SUBTASK-PART2",
            "PRODUCTION-FIRED RETURN-FROM-SUBTASK",
            "PRODUCTION-FIRED LIST-POP",
            ".*--CLEANUP-FROM-.*-BEFORE-.*",
            "Invalid chunk definition: .* names a chunk which already exists",
            " The device .* is already installed. No device installed.",
            "Productions test the .* slot in the .* buffer which is not requested or modified in any productions.",
            "Productions modify the .* slot in the .* buffer, but that slot is not used in other productions.",
            "Productions request a value for the .* slot in a request to the .* buffer, but that slot is not used in other productions.",
            "SET-BUFFER-CHUNK RETRIEVAL",
            "PRODUCTION-FIRED LIST-POP-DONE",
            "PRODUCTION-FIRED RETURN-FROM-SUBTASK-PART2",
            # fires every time we show the person something, but doesn't show what it is
            #"SET-BUFFER-CHUNK VISUAL-LOCATION",
            # these fire for every timestep
            "Stopped because time limit reached",
            "Stopped because end time already passed",
            "Stopped because no events left to process"])

        try:
            if re.search(critical, msg):
                print(msg)
                raise ValueError("Invalid ACT-R code!!! "+msg)

            if re.search(ignore, msg):
                return
            
            msg = msg.rstrip()
            # print("msg: " + msg)

            if trace_type == "warning-trace":
                msg = re.sub(r'^{0}[:\s]*'.format(re.escape('#|Warning')), '', msg)
                print("WARNING: {}".format(msg), file=sys.stderr)
                return
            
            # see if it's a task trace message
            m=re.match("time (?P<actr_time>\d+\.\d+) model (?P<actr_name>\S+) task (?P<task>\S+) depth (?P<depth>\d+) message (?P<message>\S+)\s*(?P<more>.*)", msg)
            if m is not None:
                a=m.group('more').split()
                more=dict(zip(a[::2], a[1::2]))
                cls.get_person_by_name(m.group('actr_name')).actr_trace_task(m.group('actr_time'), m.group('task'), int(m.group('depth')), m.group('message'), **more)
                return
            
            ## NOTE: a trace line is different depending on whether there is more than one model:
            #     0.050  INTEL ANALYST       PROCEDURAL             PRODUCTION-FIRED START
            #  or if there is only 1 model:
            #     0.050   PROCEDURAL             PRODUCTION-FIRED START
            #     0.000   GOAL                   SET-BUFFER-CHUNK GOAL INIT NIL
            m = re.match("\s+(?P<actr_time>[\d\.-]+)\s+"
                         "(?P<actr_name>.*?)\s*"  # both the name and trailing space are optional and don't exist if there is only 1 model
                         "(?P<actr_module>PROCEDURAL|DECLARATIVE|GOAL|VISION|AUDITORY|MOTOR|SPEECH|IMAGINAL|TEMPORAL|AUDIO)\s+"
                         "(?P<actr_cmd>\S+)\s*"
                         "(?P<actr_args>.*)\s*$", msg)

            if m is not None:
                # NOTE: actr_time is the simulation time in ACTR.
                # If used in conjunction with simpy, these may not match!!
                p = cls.get_person_by_name(m.group('actr_name'))
                assert isinstance(p, ActrPerson)
                p.actr_trace(actr_time=float(m.group('actr_time')), actr_module=m.group('actr_module'), actr_cmd=m.group('actr_cmd'), actr_args=m.group('actr_args'))
                return
            raise Exception("no match")

        except Exception as e:
            print("actr_person.dispatch_actr_trace error parsing: {}: \"{}\"".format(trace_type, msg))
            traceback.print_exc()

    def show_on_screen(self, **kwargs):
        '''
        show the specified features (names/values) onscreen, e.g. show_on_screen(x=1, msg="hi")
        The features that are manditory for actr (screen-x and screen-y) will be defaulted to 0 if not specified.
        The values of features will be passed through ActrPerson.actr_string to remove e.g. spaces. (It might be possible to preserve these through quoting?)
        '''
        self.set_current_model()
        if self.visicon_id is not None:
            actr.delete_all_visicon_features()
            self.visicon_id = None
            
        args = dict([(k,ActrPerson.actr_string(v)) for k,v in kwargs.items()])
        
        if "screen-x" not in args:
            args["screen-x"] = 0
        if "screen-y" not in args:
            args["screen-y"] = 0
            
        arglist = []
        [arglist.extend([k,v]) for k,v in args.items()]
#         print("actr_person.py: add_visicon_features for {}: {}".format(self.name, arglist))
        vis_id = actr.add_visicon_features(arglist)
        self.visicon_id = vis_id[0]

        #### note: modifying an existing visicon feature does not re-stuff the visual-location buffer so the model never 'notices' (look into this?)
        # if self.visicon_id is None:
        #     id = actr.add_visicon_features(['screen-x', 0, 'screen-y', 0, 'color', color])
        #     self.visicon_id = id[0]
        # else:
        #     id = actr.modify_visicon_features([self.visicon_id, 'color', color])
            
# these steps are done once regardless how many ActrComputerUsers are instantiated.

if actr.current_connection == None:
    raise Exception("Error: no connection to ACT-R.  Is lisp running and ACT-R loaded?")
lisp_code = "actr-person.lisp"
if not actr.load_act_r_code(lisp_code):
    raise Exception("Error loading {}".format(lisp_code))

# routing the different actr devices through dispatch_output (instead of just calling the handler method in the person directly)
# is so we can wrap the handler in an exception handler to print a warning.
for output in ['output-key', 'output-speech']:
    cmd_name = "cogtasks-"+output
    actr.add_command(cmd_name, lambda name, arg, output=output: ActrPerson.dispatch_output(name, output, arg), 'Handle simulated keypress by agents running in act-r')
    actr.monitor_command(output, cmd_name)


######
# the default in actr.py is to just print everything to standard out.
# The following code re-routes these signals to output them in a different format
# and to discard useless high-volume output, e.g. "Stopped because time limit reached" every second.
#
# There is a question here of whether to trigger program logic on the trace directly, or require
# the actr to use output devices (keyboard/speech) and interpret those.
actr.current_connection.interface.no_output()

# instead of a separate handler function for every type of trace, we route them
# to dispatch_actr_trace and provide the name of the trace as a parameter using a lambda.
for trace in ["model-trace", "command-trace", "warning-trace", "general-trace"]:
    # the code for re-wiring the traces is adapted from actr.py
    # It is confusing that there seem to be two levels of act-r "commands" necessary.
    # first, act.add_command which makes a name for the function within this process (the actr class just stores it in a dict)
    # then, send to the actr process itself an "add" message to create a command there too.
    # I am not 100% sure this is the simplest way to do it, but just doing actr.add_command
    # and trying to monitor that alias (without interface.send("add"))... does not work
    # and is not how actr.py does it.
    alias = "cogtasks-" + trace
    local_alias = alias + "-local"
    func = lambda msg, trace_type=trace : ActrPerson.dispatch_actr_trace(trace_type, msg)
    documentation = trace+" routing to python instance"
    actr.add_command(local_alias, func, documentation)
    actr.current_connection.interface.send("add", alias, local_alias, documentation, True)
    actr.current_connection.interface.send("monitor", trace, alias)

def actr_clear_all():
    actr.current_connection.evaluate_single("clear-all")

def echo_actr_output():
    actr.current_connection.evaluate_single("echo-act-r-output")

