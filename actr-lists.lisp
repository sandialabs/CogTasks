
(defun buffer-chunk-quiet (buffer) (act-r-buffer-chunk (buffer-instance buffer)))

;;;; functions for maintaining length of the list in a slot, whose name is <listname>-LENGTH
; this slot is not considered part of the cognitive model, in that the actr would not know the length of a list in declarative memory without mentally counting the elements.
; as such it is maintained with !eval! statements, not by modeling the mental arithmetic.
(defun list-length-slot (listname) (intern (format nil "~A-LENGTH" listname)))
(defun get-list-length (listname) (let ((len (chunk-slot-value-fct (buffer-read 'goal) (list-length-slot listname)))) (if len len 0)))
; set the slot that records the length of the list.  This does not modifiy the list; it merely updates the value in the slot.
; this won't work until after (extend-possible-slots slotname) has been called; this is done in push-imaginal-to-new-list instead of every time this is called.
(defun set-list-length (listname len) (set-chunk-slot-value-fct (buffer-read 'goal) (list-length-slot listname) len))
(defun add-to-list-length (listname offset) (set-list-length listname (+ (get-list-length listname) offset)))

(define-chunks retrieval next visiting print host-state-list find list-cleanup)
(chunk-type list-visitor visit-list visit-list-state visit-list-op visit-list-slot1 visit-list-value1 visit-list-slot2)
(chunk-type print-list print-list print-slot3 print-slot2 print-slot1)
(chunk-type list-element chunk-name next-chunk last-chunk)
(chunk-type push-imaginal-to-list push-imaginal-to-list)
(chunk-type push-goal-to-list push-goal-to-list)
(chunk-type list-pop list-pop list-pop-running)
(chunk-type list-push list-push)

;; visit-list iterates over the list.
;; To use visit-list,
;; First define a production (called a visitor) to fire whenever
;;   =GOAL> VISIT-LIST-STATE VISITING
;;   Your production will find the current node (chunk) in the retrieval buffer,
;;     and must leave this chunk in the retrieval buffer if traversal is to continue.
;;   When finished, to move on to the next node, it must set ==> =GOAL> VISIT-LIST-STATE NEXT
;; Then then set the VISIT-LIST slot in the goal buffer to the name of the list
;;   ==> =GOAL> visit-list mylist
;; To halt the traversal midway, your visit production should instead set:
;;   =GOAL> VISIT-LIST-STATE CLEANUP
;;   This allows you to implement a search function that halts the traversal when a match is found.
(P VISIT-LIST
   =GOAL>
   VISIT-LIST =LIST-NAME
   =LIST-NAME =CHUNK-NAME
   VISIT-LIST-STATE nil
   ?RETRIEVAL>
   STATE FREE
   ==>
   +RETRIEVAL>
   CHUNK-NAME =CHUNK-NAME
   =GOAL>
   VISIT-LIST-STATE RETRIEVAL
   )

;; Delete all the slots associated with the VISIT-LIST function.
;; This is the most comprehensive list of these slots since
;; there is no other production uses all of them.
(p VISIT-LIST-CLEANUP
   =GOAL>
   VISIT-LIST-STATE LIST-CLEANUP
   ==>
   =goal>
   VISIT-LIST nil       ;; name of the slot holding the list to be visited
   VISIT-LIST-STATE nil ;; execution control for all the VISIT-LIST productions

   VISIT-LIST-OP nil         ;; not used by VISIT-LIST directly but gives the caller a convention for triggering the desired production on each list element.
   VISIT-LIST-SLOT1 nil      ;; not used by VISIT-LIST directly, but by visitors that use 1 or more slot names
   VISIT-LIST-SLOT2 nil      ;; not used by VISIT-LIST directly, but by visitors that use 2 or more slot names
   VISIT-LIST-VALUE1 nil     ;; not used by VISIT-LIST directly, but by visitors that use a target value for 1 or more slots.
   )

;; if you try to visit a list that doesn't exist this will fire.
(P VISIT-LIST-FAILS
   =GOAL>
   VISIT-LIST =LIST-NAME
   =LIST-NAME nil
   ==>
   =GOAL>
   VISIT-LIST-STATE LIST-CLEANUP
   !OUTPUT! ("Attempted to visit list ~A which does not exist" =LIST-NAME)
   )

(P VISIT-LIST-RETRIEVE-NEXT
   =GOAL>
   VISIT-LIST-STATE NEXT
   ?RETRIEVAL>
   STATE FREE
   =RETRIEVAL>
   NEXT-CHUNK =NEXT-CHUNK
   ==>
   +RETRIEVAL>
   CHUNK-NAME =NEXT-CHUNK
   =GOAL>
   VISIT-LIST-STATE RETRIEVAL
   )

;; just finished visiting the last chunk in the list, with the slot value LAST-CHUNK t
(P VISIT-LIST-LAST-CHUNK
   =GOAL>
   VISIT-LIST-STATE NEXT
   =RETRIEVAL>
   LAST-CHUNK t
   ==>
   =GOAL>
   VISIT-LIST-STATE LIST-CLEANUP
   )
(P VISIT-LIST-READY
   =GOAL>
   VISIT-LIST-STATE RETRIEVAL
   ?RETRIEVAL>
   STATE FREE
   ==>
   =GOAL>
   VISIT-LIST-STATE VISITING
   )


;; this list visitor simply prints the chunk
;; To call it:
;; ==>
;;   =GOAL>
;;     visit-list mylist
;;     visit-list-op print
;;     visit-list-slot1 myslot1 ;; optional; if specified, only this slot (instead of the whole chunk) is printed
;;     visit-list-slot2 myslot2 ;; optional; if specified (along with visit-list-slot1), then these 2 slots are printed.

(p visit-list-print
   =GOAL>
   VISIT-LIST-STATE VISITING
   VISIT-LIST-OP print
   VISIT-LIST-SLOT1 nil
   ==>
   !eval! (buffer-chunk-quiet 'retrieval)
   =GOAL>
   VISIT-LIST-STATE NEXT
   )

;; print just the slot1 named in print-slot1
(p visit-list-print-slot
   =GOAL>
   VISIT-LIST-STATE VISITING
   VISIT-LIST-OP print
   VISIT-LIST-SLOT1 =slot1
   VISIT-LIST-SLOT2 nil
   =retrieval>
   =slot1 =value1
   ==>
   !OUTPUT! ("~A" =value1)
   =GOAL>
   VISIT-LIST-STATE NEXT
   =retrieval>
   )

;; print just the slots named in print-slot1 and print-slot2
(p visit-list-print-slots2
   =GOAL>
   VISIT-LIST-STATE VISITING
   VISIT-LIST-OP print
   VISIT-LIST-SLOT1 =slot1
   VISIT-LIST-SLOT2 =slot2
   PRINT-SLOT3 nil
   =retrieval>
   =slot1 =value1
   =slot2 =value2
   ==>
   !OUTPUT! ("~A ~A" =value1 =value2)
   =GOAL>
   VISIT-LIST-STATE NEXT
   =retrieval>
   )

(p view-request-to-print-list
   =visual-location>
   print-list =listname
   print-slot1 nil
   =goal>
   ==>
   =goal>
   VISIT-LIST =listname
   VISIT-LIST-OP print
   )

(p view-request-to-print-slot
   =visual-location>
   print-list =listname
   print-slot1 =slot1
   print-slot2 nil
   =goal>
   ==>
   =goal>
   VISIT-LIST =listname
   VISIT-LIST-OP print
   VISIT-LIST-SLOT1 =slot1
   VISIT-LIST-SLOT2 nil
   )

(p view-request-to-print-slots
   =visual-location>
   print-list =listname
   print-slot1 =slot1
   print-slot2 =slot2
   =goal>
   ==>
   =goal>
   VISIT-LIST =listname
   VISIT-LIST-OP print
   VISIT-LIST-SLOT1 =slot1
   VISIT-LIST-SLOT2 =slot2
   PRINT-SLOT3 nil
   )

(p view-request-for-list-pop
   =visual-location>
   list-pop =listname
   =goal>
   ==>
   =goal>
   list-pop =listname
   )

;; visit-list-find is a list visitor to find the most recent chunk with the specified values for the specified slot.
;; To call it:
;; ==>
;;   =GOAL>
;;     visit-list mylist
;;     visit-list-op find
;;     visit-list-slot1 myslot1 ;; find the chunk with a slot named 'myslot1' whose value is 'myvalue1'
;;     visit-list-value1 myvalue1
;;
;; if found, the matching chunk is left in the retrieval buffer.

(p visit-list-find-mismatch
   =goal>
   VISIT-LIST-OP find
   VISIT-LIST-STATE VISITING
   VISIT-LIST-SLOT1 =SLOT1
   VISIT-LIST-VALUE1 =VALUE1
   =retrieval>
   - =SLOT1 =VALUE1
   =SLOT1 =BADVALUE
   ==>
   =goal>
   VISIT-LIST-STATE NEXT
   ;;!output! ("Looking for ~A = ~A but found ~A" =SLOT1 =VALUE1 =BADVALUE)
   =retrieval>
   )

(p get-list-find-match
   =goal>
   VISIT-LIST-OP find
   VISIT-LIST-STATE VISITING
   VISIT-LIST-SLOT1 =SLOT1
   VISIT-LIST-VALUE1 =VALUE1
   =retrieval>
   =SLOT1 =VALUE1
   ==>
   !OUTPUT! ("Found ~A = ~A" =SLOT1 =VALUE1)
   =goal>
   VISIT-LIST-STATE LIST-CLEANUP
   =retrieval>
   )


;; push-imaginal-to-list
;; Add the chunk from the imaginal buffer to the specified list.  The imaginal buffer will be cleared.
;; To invoke, set the push-imaginal-to-list slot in the goal buffer to the name of the list,
(p push-imaginal-to-list
   =goal>
   push-imaginal-to-list =listname
   =listname =cdr
   =imaginal> ;; imaginal buffer must contain a chunk for us to link into the list
   !bind! =car (buffer-chunk-quiet 'imaginal)   
   ==>
   !eval! (add-to-list-length =listname 1)
   =imaginal>
   chunk-name =car ;; link the chunk into the list
   next-chunk =cdr
   =goal>
   =listname =car  ;; update the car (head) of the list
   push-imaginal-to-list nil ;; prevent repetitive firing of this production
   -imaginal>  ;; this stores the chunk in the imaginal buffer to declarative memory.  If we don't do this it will fail to retrieve the chunk later.
   )

;; if push-imaginal-to-list is called but the list doesn't exist yet, push-imaginal-to-new-list matches instead.
(p push-imaginal-to-new-list
   =goal>
   push-imaginal-to-list =listname
   =listname nil
   =imaginal> ;; imaginal buffer must contain a chunk for us to link into the list
   !bind! =car (buffer-chunk-quiet 'imaginal)
   ==>
   !eval! (extend-possible-slots (list-length-slot =listname) nil) ;; create a slot for the length of the list,
   !eval! (set-list-length =listname 1) ;; and initialize it to 1
   =imaginal>
   chunk-name =car ;; link the chunk into the list
   next-chunk nil
   last-chunk t
   =goal>
   =listname =car  ;; update the car (head) of the list
   push-imaginal-to-list nil ;; prevent repetitive firing of this production
   -imaginal>  ;; this stores the chunk in the imaginal buffer to declarative memory.  If we don't do this it will fail to retrieve the chunk later.
   )

;; push-goal-to-list
;; Add the chunk from the goal buffer to the specified list.  The goal buffer will be cleared TODO
;; To invoke, set the push-goal-to-list slot in the goal buffer to the name of the list,
(p push-goal-to-list
   =goal>
   push-goal-to-list =listname
   =listname =cdr
   !bind! =car (buffer-chunk-quiet 'goal)
   ==>
   =goal>
   chunk-name =car ;; link the chunk into the list
   next-chunk =cdr
   =listname =car  ;; update the car (head) of the list
   -goal>  ;; this stores the chunk in the goal buffer to declarative memory.  If we don't do this it will fail to retrieve the chunk later.
   )

;; if push-goal-to-list is called but the list doesn't exist yet, push-goal-to-new-list matches instead.
(p push-goal-to-new-list
   =goal>
   push-goal-to-list =listname
   =listname nil
   !bind! =car (buffer-chunk-quiet 'goal)   
   ==>
   =goal>
   chunk-name =car ;; link the chunk into the list
   next-chunk nil
   last-chunk t
   =listname =car  ;; update the car (head) of the list
   push-goal-to-list nil ;; prevent repetitive firing of this production
   -goal>
   )

;; place the chunk at the head into the retrieval buffer and remove it from the list.
;; To invoke, set the list-pop slot in the goal buffer to the name of the list.
;; Note this is not really the inverse of push-imaginal since it stores from the imaginal buffer
;; whereas this retrieves into the retrieval buffer.  This by design in ACT-R; it doesn't
;; support creating a new chunk with +retrieval> (this does a retrieval search instead),
;; whereas retrievals automatically go to the retreival buffer, not imaginal.
(p list-pop
   =goal>
   list-pop =listname
   =listname =car
   list-pop-running nil
   ?retrieval>
   state free
   ==>
   !eval! (add-to-list-length =listname -1)
   +retrieval> chunk-name =car
   =goal>
   list-pop-running t
   )

(p list-pop-done
   =goal>
   list-pop =listname
   =listname =car
   list-pop-running t
   =retrieval>
   chunk-name =car
   next-chunk =cdr
   ==>  
   =goal>
   list-pop nil
   =listname =cdr
   list-pop-running nil
   =retrieval>
   )

(p list-pop-last-done
   =goal>
   list-pop =listname
   =listname =car
   list-pop-running t
   =retrieval>
   chunk-name =car
   last-chunk t
   ==>  
   =goal>
   list-pop nil
   =listname nil
   list-pop-running nil
   =retrieval>
   )
