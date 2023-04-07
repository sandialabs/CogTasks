
; (readslots-names (buffer-read 'goal) '(x y)) => (X 1 Y 2)
; (defun readslots-names (chunk slots)
;  (apply 'append (map 'list (lambda (s) (list s (chunk-slot-value-fct chunk s))) slots)))

; (readslots (buffer-read 'goal) '(x y)) => (1 2)
(defun readslots (chunk slots)
  (map 'list (lambda (s) (chunk-slot-value-fct chunk s)) slots))

(defun task-trace (msg &rest goal-slots)
  (let* ((goalchunk (buffer-read 'goal))
	 (task-state (chunk-slot-value-fct goalchunk 'task-state))
	 (task (chunk-slot-value-fct goalchunk (if (eq task-state 'subtask) 'subtask 'task))) ;if in the process of starting a subtask, report as the new subtask
	 (message (apply 'format (append (list nil msg) (readslots goalchunk goal-slots))))
	 (s (format nil "~{~A~^ ~}" (append (list
					      "time" (mp-time)
					      "model" (current-model)
					      "task" task
					      "depth" (get-list-length 'current-tasks)
					      "message" message)))))
	 (model-output s))
       t) ; always return t so that eval'ing as a condition in a production won't possibly prevent it from firing.

(defun task-trace-start () (task-trace "start"))
(defun task-trace-end () (task-trace "end"))

    (define-chunks current-tasks return-from-subtask start-subtask)
    (chunk-type task current-tasks subtask task task-state)

    (load "actr-lists.lisp")

    ;; define states used by all functions.
    ;; each function uses a goal slot with the name of the function to control its state.
    ;; e.g. to call a function, set =goal> <function> start
    (define-chunks
    start   ;; set by the caller to trigger the function to start. Any other parameters needed should be documented at the constructor
    cleanup ;; triggers the function to erase its slots and set its state slot to done
    subtask
    done)   ;; notifies the caller that it has finished.

    (p start-subtask
    =goal>
    task-state subtask
    - task start-subtask
    task =task
    subtask =subtask
    ?imaginal> state free
    =imaginal>
    ==>
    =imaginal>
    task =task
    =goal>
    push-imaginal-to-list current-tasks
    task start-subtask
    )

    (p start-subtask-part2
    =goal>
    task start-subtask
    subtask =subtask
    ?imaginal> state free buffer empty
    ==>
    =goal>
    task =subtask
    subtask nil
    task-state start
    !eval! (task-trace-start)        
    )

    (p return-from-subtask
    =goal>
    task =task
    task-state done
    current-tasks =current-tasks
    ==>
    =goal>
    list-pop current-tasks
    task-state return-from-subtask
    !eval! (task-trace-end)
    )

    (p return-from-subtask-part2
    =goal>
    task-state return-from-subtask
    list-pop nil
    =retrieval>
    task =task
    task-state =task-state
    ==>
    =goal>
    task =task
    task-state =task-state
    =retrieval>
    )
