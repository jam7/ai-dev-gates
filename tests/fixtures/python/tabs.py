def tabbed(items):
	"""Indented with tabs, which expandtabs has to normalize."""
	for item in items:
		if item:
			for part in item:
				if part:
					return part
	return None
