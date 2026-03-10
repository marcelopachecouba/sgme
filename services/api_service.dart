import 'dart:convert';
import 'package:http/http.dart' as http;

class ApiService {

  static const baseUrl = "https://sgme.onrender.com";

  static Future<List<dynamic>> minhasEscalas() async {

    final response = await http.get(
      Uri.parse("$baseUrl/api/minhas_escalas"),
    );

    if (response.statusCode == 200) {

      return jsonDecode(response.body);

    } else {

      throw Exception("Erro ao carregar escalas");

    }
  }
}