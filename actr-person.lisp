
(defun read-eval-string (s) (eval (read-from-string (format nil "(progn ~A)" s))))
(add-act-r-command "read-eval-string" 'read-eval-string)

(clear-all)


(defun ticks-for-seconds (s) (/ (log (+ 1 (/ (* s (- (get-parameter-default-value :time-mult) 1)) (get-parameter-default-value :time-master-start-increment)))) (log (get-parameter-default-value :time-mult))))

(add-act-r-command "clear-all" 'clear-all "clear-all")
(add-act-r-command "echo-act-r-output" 'echo-act-r-output "echo-act-r-output")
