function listPatientFeedback(filters) {
  var params = new URLSearchParams();
  params.set('page', String(filters.page));
  params.set('page_size', String(filters.pageSize));
  if (filters.target) params.set('target', filters.target);
  if (filters.category) params.set('category', filters.category);
  return request('/admin/patient-feedback?' + params.toString());
}
