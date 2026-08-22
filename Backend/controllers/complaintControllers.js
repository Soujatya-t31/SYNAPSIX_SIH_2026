const Complaint = require('../models/complaint');

exports.createComplaint = async (req, res) => {
  try {
    const { category, description, severity, latitude, longitude } = req.body;

    // 2. MAKE SURE THIS MATCHES THE IMPORTED VARIABLE (Capital C)
    const newComplaint = new Complaint({
      category,
      description,
      severity: severity || 'Low',
      location: {
        latitude: latitude ? parseFloat(latitude) : null,
        longitude: longitude ? parseFloat(longitude) : null
      },
      mediaPath: req.file ? `/uploads/${req.file.filename}` : null
    });

    await newComplaint.save();
    
    res.status(201).json({ 
      success: true, 
      message: 'Complaint registered successfully!', 
      data: newComplaint 
    });
  } catch (error) {
    console.error('Error saving complaint:', error); // Prints exact error in server terminal
    res.status(500).json({ 
      success: false, 
      message: 'Server error while filing complaint', 
      error: error.message 
    });
  }
};

exports.getAllComplaints = async (req, res) => {
  try {
    const complaints = await Complaint.find().sort({ createdAt: -1 });
    res.status(200).json({
      success: true,
      data: complaints
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      message: 'Error fetching complaints',
      error: error.message
    });
  }
};
exports.deleteComplaint = async (req, res) => {
  try {
    const { id } = req.params;
    const deletedComplaint = await Complaint.findByIdAndDelete(id);

    if (!deletedComplaint) {
      return res.status(404).json({ success: false, message: 'Complaint not found' });
    }

    res.status(200).json({ success: true, message: 'Complaint deleted successfully' });
  } catch (error) {
    res.status(500).json({ success: false, message: 'Error deleting complaint', error: error.message });
  }
};