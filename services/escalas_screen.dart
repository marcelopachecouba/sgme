import 'package:flutter/material.dart';
import '../services/api_service.dart';

class EscalasScreen extends StatefulWidget {

  @override
  _EscalasScreenState createState() => _EscalasScreenState();
}

class _EscalasScreenState extends State<EscalasScreen> {

  List escalas = [];

  @override
  void initState() {
    super.initState();
    carregar();
  }

  carregar() async {

    final dados = await ApiService.minhasEscalas();

    setState(() {
      escalas = dados;
    });

  }

  @override
  Widget build(BuildContext context) {

    return Scaffold(

      appBar: AppBar(
        title: Text("Minhas Escalas"),
      ),

      body: ListView.builder(

        itemCount: escalas.length,

        itemBuilder: (context, index) {

          final e = escalas[index];

          return Card(

            child: ListTile(

              title: Text(e["comunidade"]),

              subtitle: Text(
                "${e["data"]} - ${e["horario"]}"
              ),

            ),

          );
        },

      ),

    );
  }
}