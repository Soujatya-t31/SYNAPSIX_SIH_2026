const mongoose = require("mongoose");
const complaintSchema = new mongoose.Schema({
    category: {
        type: String,
        required: true,
        enum:[
            'Road/Pothole', 'Streetlight', 'Garbage', 'Drainage', 
            'Water Leakage', 'Traffic Signal', 'Public Toilet', 
            'Footpath', 'Bridge', 'Public Building', 'Other'
        ]
    },
    description: {type: String , required: true}, 
    severity: {
        type: String,
        enum: ['Low' , 'Medium' , 'High' , 'Dangerous'],
        default: 'Low'
    },
    location: {
        latitude: {type: Number},
        longitude: {type: Number},
    },
    mediaPath: {type: String},
    createdAt: {type: Date , default: Date.now}

});

module.exports  = mongoose.model('complaint' , complaintSchema);