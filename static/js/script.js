$(document).ready(function() {
    // Fungsi untuk menangani perubahan pada input tanggal
    $('#startDate, #endDate').change(function() {
        var startDate = $('#startDate').val();
        var endDate = $('#endDate').val();

        $('#logsTableBody tr').each(function() {
            var entryDate = $(this).find('td:eq(2)').text(); // Ambil tanggal dari kolom 'Created'

            if (startDate && endDate) {
                if (entryDate >= startDate && entryDate <= endDate) {
                    $(this).show();
                } else {
                    $(this).hide();
                }
            } else {
                $(this).show(); // Tampilkan semua baris jika tanggal tidak dipilih
            }
        });
    });
});
