const express = require("express");
const router = express.Router();

const upload = require('../middleware/upload');
const {createComplaint , getAllComplaint, getAllComplaints, deleteComplaint} = require("../controllers/complaintControllers");

router.post('/' , upload.single('media') , createComplaint);
router.get('/' , getAllComplaints);
router.delete('/:id', deleteComplaint);

module.exports = router;