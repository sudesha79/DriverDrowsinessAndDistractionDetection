
from __future__ import print_function
import sys, struct, json, base64, os.path

FSDK_signature = 0x4b445346
FSDK_template_size = 1040

read_data = lambda f, sig, n, s: struct.unpack(sig, f.read(s))[0] if n==1 else struct.unpack(sig*n, f.read(n*s))
read_byte = lambda f, n=1: read_data(f, 'B', n, 1)
read_int = lambda f, n=1: read_data(f, 'i', n, 4)
read_long = lambda f, n=1: read_data(f, 'q', n, 8) # qword: 64 bit OS long
read_float = lambda f, n=1: read_data(f, 'f', n, 4)

write_data = lambda f, sig, *v: f.write(struct.pack(sig*len(v), *v))
write_byte = lambda f, *v: write_data(f, 'B', *v)
write_int = lambda f, *v: write_data(f, 'i', *v)
write_long = lambda f, *v: write_data(f, 'q', *v) # qword: 64 bit OS long
write_float = lambda f, *v: write_data(f, 'f', *v)


class FSDKTrackerDataError(Exception): pass


class TrackerData:
	json_fields = {'info', 'version', 'frames_num', 'faces_num', 'profiles', 'faces',
		'max_id', 'max_seq_id', 'reassignments', 'merges', 'attributes'}
	info = "FSDK"
	# we repeat FSDK tracker data file structure here
	class Face:
		json_fields = {'id', 'face_id', 'frame_id', 'template', 'image'}
		class Image:
			json_fields = {'mode', 'format', 'width', 'height', 'data', 'features'}
			def __init__(self, dct = {}): self.__dict__.update(dct)
		def __init__(self, f):
			self.image = None
			if type(f) is dict:
				self.__dict__.update(f)
				self.template = base64.b64decode(self.template)
				if self.image:
					self.image.data = base64.b64decode(self.image.data)
					self.image.features = base64.b64decode(self.image.features)
			else:
				self.id, ts = read_int(f, 2)
				if ts != FSDK_template_size:
					raise FSDKTrackerDataError("Incorrect template size")
				self.template = f.read(ts)
				self.frame_id, self.face_id = read_long(f, 2)
				if read_byte(f): # is cropped face present ?
					img = self.image = TrackerData.Face.Image()
					img.mode, img.format, img.width, img.height, size = read_int(f, 5)
					img.data, img.features = f.read(size), f.read(70*2*4)

		def write_to_binary(face, f):
			write_int(f, face.id, FSDK_template_size)
			f.write(face.template)
			write_long(f, face.frame_id, face.face_id)
			write_byte(f, face.image is not None)
			if face.image:
				img = face.image
				write_int(f, img.mode, img.format, img.width, img.height, len(img.data))
				f.write(img.data)
				f.write(img.features)

	def __init__(self): pass

	@classmethod
	def from_binary(cls, filename):
		""" return new TrackerData object loaded from FaceSDK compatible binary file """
		def __read_merge(f):
			size = read_int(f)
			return dict(name=f.read(size)[:-1].decode('utf-8'), data=read_int(f, read_int(f)//4))
		with open(filename, 'rb') as f:
			self = TrackerData()
			if read_int(f) != FSDK_signature:
				raise FSDKTrackerDataError("Invalid file format")
			self.version = read_int(f)
			if self.version != 6:
				raise FSDKTrackerDataError("Incorrect version of tracker data file: %i" % self.version)
			self.frames_num, self.faces_num = read_long(f, 2)
			read_profile = lambda : (read_int(f), f.read(read_int(f))[:-1].decode('utf-8')) # id, name
			profiles = (read_profile() for p in range(read_int(f)))
			self.profiles = dict(p for p in profiles if p[1])
			self.faces = [TrackerData.Face(f) for p in range(read_int(f))]
			self.max_id, self.max_seq_id = read_int(f, 2)			
			self.reassignments = [{'reassigned_id': read_int(f), 'new_id': read_int(f)} for r in range(read_int(f))]
			self.reassign_ids()
			self.merges = [__read_merge(f) for r in range(read_int(f))]
			self.attributes = []
			try:
				for r in range(read_int(f)):
					self.attributes.append({'id': read_int(f), 'attr_info1': read_int(f), 'attr_info2': read_float(f)})
			except:
				print("The file is corrupted: some face attributes were ignored")
			self.source_file, self.source_type = filename, 'bin'
			return self

	@classmethod
	def from_json(cls, filename):
		""" return new TrackerData object loaded from json file """
		def hook(dct):
			if dct.get('info') == TrackerData.info:
				td = TrackerData()
				td.__dict__.update(dct)
				if td.version != 6:
					raise FSDKTrackerDataError("Tracker version is incorrect: %i" % td.version)
				td.profiles = {int(key): val for key, val in td.profiles.items() if val}				
				td.reassign_ids()
				return td
			if 'template' in dct: return TrackerData.Face(dct)
			if TrackerData.Face.Image.json_fields.issubset(dct): return TrackerData.Face.Image(dct)
			return dct
		with open(filename, 'r') as f:
			tracker = json.loads(f.read(), object_hook = hook)
		if type(tracker) is not TrackerData:
			raise FSDKTrackerDataError("The json file is not FaceSDK tracker data file or it is corrupted")
		tracker.source_file = filename
		tracker.source_type = 'json'
		return tracker

	@classmethod
	def from_file(cls, filename):
		with open(filename, 'rb') as f:
			sig = read_int(f)
		if sig == FSDK_signature:
			return TrackerData.from_binary(filename)
		return TrackerData.from_json(filename)

	def save_to_binary(self, filename):
		""" save TrackerData object to FaceSDK compatible binary file """
		with open(filename, 'wb') as f:
			write_int(f, FSDK_signature, self.version)
			write_long(f, self.frames_num, self.faces_num)

			write_int(f, len(self.profiles))
			for id, name in self.profiles.items():
				write_int(f, id, len(name)+1)
				f.write(name.encode())
				write_byte(f, 0)

			write_int(f, len(self.faces))
			for face in self.faces: face.write_to_binary(f)

			write_int(f, self.max_id, self.max_seq_id)

			write_int(f, len(self.reassignments))
			for r in self.reassignments:
				write_int(f, r['reassigned_id'], r['new_id'])

			write_int(f, len(self.merges))
			for m in self.merges:
				write_int(len(m['name'])+1)
				f.write(m['name'].encode())
				write_byte(f, 0)
				write_int(f, len(m['data'])//4, *m['data'])

			write_int(f, len(self.attributes))
			for m in self.attributes:
				write_int(f, m['id'], m['attr_info1'])
				write_float(f, m['attr_info2'])

	def save_to_json(self, filename):
		""" save TrackerData object to json file """
		class json_encoder(json.JSONEncoder):
			def default(self, obj):
				if hasattr(obj, 'json_fields'):
					return {f: getattr(obj, f) for f in obj.json_fields if getattr(obj, f) is not None}
				if type(obj) is bytes:
					return base64.b64encode(obj).decode('utf-8')
				return json.JSONEncoder.default(self, obj)
		with open(filename, 'w') as f:
			print(json.dumps(self, indent=4, cls = json_encoder), file = f)

	def remove_image_data(self):
		for f in self.faces:
			f.image = None

	def remove_profile(self, id):
		cnt = len(self.faces)
		self.faces = [f for f in self.faces if f.id != id]
		if id in self.profiles: self.profiles.pop(id)
		return cnt != len(self.faces)

	def extract_profile(self, id):
		faces = [f for f in self.faces if f.id == id]
		if not faces:
			return False
		if id in self.profiles: 
			self.profiles = {id: self.profiles[id]}
		self.faces = faces
		return True

	def __get_faces(self):
		class face_id:
			def __init__(self, face, name):
				self.name, self.faces, self.data = name, [face], {face.template}
			def add_face(self, *face):
				for f in face:
					if f.template not in self.data:
						self.data.add(f.template)
						self.faces.append(f)
			def has_common(self, face): return self.data & face.data
		faces = {}
		for f in self.faces:
			if f.id in faces:
				faces[f.id].add_face(f)
			else:
				faces[f.id] = face_id(f, self.profiles.get(f.id, ''))
		return faces

	def reassign_ids(self):
		reassignments = {r['reassigned_id'] : r['new_id'] for r in self.reassignments if r['reassigned_id'] != r['new_id']}
		for f in self.faces:
			if f.id in reassignments:
				f.id = reassignments[f.id]
		self.reassignments = []

	def merge(self, *tdl):
		faces = self.__get_faces()
		names = {v:k for k,v in self.profiles.items()}
		self.max_id = max(faces.keys()) if faces else 1
		def iter_faces(faces):
			for id, f in faces.items():
				for face in f.faces:
					face.id = id
					yield face
		def merge_single(td):
			faces2 = td.__get_faces()
			for id2, f2 in faces2.items():
				if f2.name:
					if f2.name in names: id2 = names[f2.name]
					elif id2 in faces:
						self.max_id += 1
						id2 = self.max_id
					self.profiles[id2] = f2.name
				if id2 not in faces: faces[id2] = f2
				else:
					if faces[id2].has_common(f2) or f2.name in names:
				 		faces[id2].add_face(*f2.faces)
					else:
				 		self.max_id += 1
				 		faces[self.max_id] = f2
			self.faces = list(iter_faces(faces))

		for td in tdl: merge_single(td)

	def __getattr__(self, item):
		if item == 'images':
			return tuple(f.image for f in self.faces if f.image)
		raise AttributeError(item)

	def statistics(self):
		if len(self.faces):
			with_images = len(self.images)
			finfo = "{cnt} (with images: {n})".format(cnt = len(self.faces), 
				n = 'all' if with_images == len(self.faces) else with_images)
		else:
			finfo = "{}".format(len(self.faces))
		stat_info = "file version: {v}\nframesNum: {fr}\nfacesNum: {fa}\nprofiles: {pr}\nfaces: {faces}\n"\
			"max_id: {maxid}\nmax seq id: {mseqid}\nreassignments: {reas}\nmerges: {mgs}\nattributes: {attrs}".format(
				v = self.version, fr = self.frames_num, fa = self.faces_num, pr = len(self.profiles),
				faces = finfo, maxid = self.max_id, mseqid = self.max_seq_id,
				reas = len(self.reassignments), mgs = len(self.merges), attrs = len(self.attributes)
			)
		return stat_info


if __name__ == '__main__':
	options = []
	output_file = ''
	skip_image_data = False
	face_image_id = None
	remove_id = extract_id = None
	input_files = [p for p in sys.argv[1:] if not p.startswith('-') or options.append(p)]
	if not input_files:
		print("\nFaceSDK Tracker Data converter, version 1.7")
		print("Usage:")
		print("\ttrackerMemoryTool.py <input file(s)> [options]")
		print("\toptions:")
		print('\t-o<output file>')
		print('\t-sid\tskip image data')
		print('\t-profileid<id>\textract face images for profile id (requires pillow library)')
		print('\t-remove<id>\tremove profile id')
		print('\t-extract<id>\textract profile id')
		print("Note:")
		print('\tInput and output files are to be of FSDK binary or json formats.')
		print('\tMultiple input files will be merged.')
		print('\tThe trackerMemoryTool will automatically determine the format of the source file and generate a new file in a different format (.dat -> .json or .json -> .dat) with the name outputfile.json or outputfile.dat')
		exit(0)

	for o in options:
		if o.startswith('-o'): output_file = o[2:]
		elif o.startswith('-sid'): skip_image_data = True
		elif o.startswith('-profileid'): face_image_id = int(o[10:])
		elif o.startswith('-remove'): remove_id = int(o[7:])
		elif o.startswith('-extract'): extract_id = int(o[8:])
		else:
			raise FSDKTrackerDataError("Unrecognized option '%s'" % o[:2])
	if not output_file and face_image_id is None:
		if len(input_files) == 1:
			output_file = os.path.splitext(input_files[0])[0]+'.'
		else:
			raise FSDKTrackerDataError("Output file is not specified")
	trackers = [TrackerData.from_file(f) for f in input_files]
	if skip_image_data:
		for t in trackers: t.remove_image_data()
	td = trackers[0]
	if len(trackers) == 1:
		if output_file.endswith('.'):
			output_file += 'json' if td.source_type == 'bin' else 'dat'
	else:
		td.merge(*trackers[1:])
		if output_file.endswith('.'):
			output_file += 'json' if td.source_type == 'json' else 'dat'

	if remove_id is not None:
		if not td.remove_profile(remove_id):
			print("Faces with profile id", remove_id, "are not found.")
			exit(1)

	if extract_id is not None:
		if not td.extract_profile(extract_id):
			print("Faces with profile id", extract_id, "are not found.")
			exit(1)

	if output_file:
		outfmt = 'json' if output_file.endswith('json') else 'binary'
		if outfmt == 'json':
			td.save_to_json(output_file)
		else:
			td.save_to_binary(output_file)
	print(td.statistics())
	if output_file:
		if remove_id is not None:
			print("\nFaces with profile id", remove_id, "are removed.")
		if extract_id is not None:
			print("\nFaces with profile id", extract_id, "are extracted.")
		print("\nFile '{}' is created in {} format.".format(output_file, outfmt))
	if face_image_id is not None:
		print()
		faces = [face for face in td.faces if face.id == face_image_id]
		if not faces:
			print("Faces with profile id", face_image_id, "are not found.")
		else:
			faces = [face for face in faces if face.image]
			if not faces:
				print("Faces with profile id", face_image_id, "do not have images.")
			else:
				from PIL import Image
				for face in faces:
					im = Image.frombytes('L', (face.image.width, face.image.height), face.image.data)
					fname = "face%s_%s.png"%(face_image_id, face.face_id)
					im.save(fname)
					print("Image file", fname, "is created")

