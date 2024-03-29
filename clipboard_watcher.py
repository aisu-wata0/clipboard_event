
import time
import threading
import pyperclip
import logging

def ctype_async_raise(thread_obj, exception):
	import ctypes
	found = False
	target_tid = 0
	for tid, tobj in threading._active.items():
		if tobj is thread_obj:
			found = True
			target_tid = tid
			break

	if not found:
		raise ValueError("Invalid thread object")

	ret = ctypes.pythonapi.PyThreadState_SetAsyncExc(
		target_tid, ctypes.py_object(exception))
	# ref: http://docs.python.org/c-api/init.html#PyThreadState_SetAsyncExc
	if ret == 0:
		raise ValueError("Invalid thread ID")
	elif ret > 1:
		# Huh? Why would we notify more than one threads?
		# Because we punch a hole into C level interpreter.
		# So it is better to clean up the mess.
		ctypes.pythonapi.PyThreadState_SetAsyncExc(target_tid, 0)
		raise SystemError("PyThreadState_SetAsyncExc failed")
	print("Successfully set asynchronized exception for", target_tid)


# example predicate
def is_url(clipboard_content):
	return True

# example callback
def print_to_stdout(clipboard_content):
	print("Found url: %s" % str(clipboard_content), flush=True)


class ClipboardWatcher(threading.Thread):
	def __init__(
		self,
		predicate,
		callback,
		cooldown=0.1,
		discard_empty=True,
		linear_threads=True,
		queue_text_events=True,
		**kwargs,
	):
		"""
		"""
		super().__init__(**kwargs)
		self._predicate = predicate
		self._callback = callback
		self._cooldown = cooldown
		self._stopping = False
		self._paused = False
		self._threads = []
		self._discard_empty = discard_empty
		self._linear_threads = linear_threads
		self.queue_text_events = queue_text_events
		if not self.queue_text_events:
			self._linear_threads= True
		self._last_thread = None
		self._last_idx = 0

	def run(self):
		# Initialize with current clipboard content
		recent_value = pyperclip.paste()
		while not self._stopping:
			# If content changed
			tmp_value = None
			try:
				tmp_value = pyperclip.paste()
			except:
				pass
			if tmp_value and tmp_value != recent_value:
				if not self._paused:
					# Update recent_value with current content
					recent_value = tmp_value
					text = self._predicate(tmp_value)
					if text:
						if len(self._threads) == 0 or (len(self._threads) > 0 and self.queue_text_events):
							thread = self._callback(text)
							self._threads.append(thread)
							if not self._linear_threads:
								thread.start()

			if self._linear_threads:
				if self._last_thread and not self._last_thread.is_alive():
					self._last_thread.join()
					self._threads.pop(self._last_idx)
					self._last_thread = None
				
				if not self._last_thread:
					if len(self._threads) > self._last_idx:
						# self._last_idx = len(self._threads) - 1
						self._last_thread = self._threads[self._last_idx]
						self._last_thread.start()

			time.sleep(self._cooldown)

	def pause(self):
		self._paused = True

	def unpause(self):
		self._paused = False

	def stop(self):
		self._stopping = True
		for thread in self._threads:
			if not thread.is_alive():
				try:
					thread.join()
				except Exception as e:
					if "cannot join thread before it is started" in str(e):
						continue
					print(str(e))
			else:
				try:
					ctype_async_raise(thread, SystemExit)
				except ValueError:
					pass
				except:
					logging.exception("while killing threads")
					continue
				if thread.is_alive():
					while True:
						try:
							thread._stop()
							break
						except:
							pass
		self._stopping = False
